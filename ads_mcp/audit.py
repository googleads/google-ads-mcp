# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Audit logging middleware and PII/binary argument redaction for MCP tool calls."""

from __future__ import annotations

from collections.abc import Mapping, Set as AbstractSet
import contextlib
import datetime
from enum import StrEnum
import functools
import hashlib
import inspect
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any
import uuid

from fastmcp.exceptions import (
    DisabledError,
    FastMCPError,
    NotFoundError,
    ToolError,
    ValidationError,
)
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import Tool, ToolResult
from fastmcp.tools.function_tool import FunctionTool
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.interceptors import helpers as ga_helpers
from google.ads.googleads.interceptors.interceptor import Interceptor
from google.protobuf.message import Message as PbMessage
from mcp import types as mcp_types
import proto
from pydantic import TypeAdapter, ValidationError as PydanticValidationError

from ads_mcp import utils

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from key_value.aio.protocols import AsyncKeyValue

audit_logger = logging.getLogger("ads_mcp.audit")
# Dedicated sibling logger so plain-text storage errors do not pollute JSON-only
# log handlers attached to "ads_mcp.audit".
_storage_logger = logging.getLogger("ads_mcp.audit_storage")

AUDIT_COLLECTION = "ads_mcp_audit"

REDACTED_MASK: str = getattr(Interceptor, "_SENSITIVE_INFO_MASK", "REDACTED")


class MutationPhase(StrEnum):
    """Execution phase of an MCP tool call with respect to account mutation."""

    READ = "READ"
    PROPOSE = "PROPOSE"
    COMMIT = "COMMIT"


class AuditStatus(StrEnum):
    """Outcome classification of an audited MCP tool call or background task."""

    COMPLETED = "completed"
    EMPTY = "empty"
    ENQUEUED = "enqueued"
    ERROR = "error"
    FAILED = "failed"


_BOOL_ADAPTER: TypeAdapter[bool] = TypeAdapter(bool)

# Maximum characters retained per logged string argument before truncation,
# protecting Cloud Logging (256 KB) and Firestore (1 MiB) limits.
_MAX_STRING_LENGTH = 4096
_EMAIL_SCAN_LOOKAHEAD = 320
_MIN_BASE64_REDACT_LEN = 512

_CAMEL_BOUNDARY_1_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_BOUNDARY_2_RE = re.compile(r"([a-z0-9])([A-Z])")


def _normalize_key(key: str) -> str:
    """Normalizes camelCase, PascalCase, and hyphenated keys to lowercase snake_case."""
    step1 = _CAMEL_BOUNDARY_1_RE.sub(r"\1_\2", key)
    step2 = _CAMEL_BOUNDARY_2_RE.sub(r"\1_\2", step1)
    return step2.replace("-", "_").lower()


# Guard access to private google-ads-python helper attributes so upstream
# refactors cannot break MCP server startup.
_UPSTREAM_SENSITIVE_MAP: Mapping[str, Any] = getattr(
    ga_helpers, "_MESSAGES_WITH_SENSITIVE_FIELDS", {}
)
_mask_proto_message = getattr(ga_helpers, "mask_message", None)

_BASELINE_SENSITIVE_PATHS: frozenset[str] = frozenset(
    {
        "email_address",
        "inviter_user_email_address",
        "user_email",
        "request_user_email",
        "places_location_feed_data.email_address",
        "contact_details.phone_number",
        "contact_details.phone_number_extension",
        "contact_details.email",
        "contact_details.consumer_name",
        "message_details.text",
    }
)

_SENSITIVE_FIELD_PATHS: frozenset[str] = frozenset(
    _BASELINE_SENSITIVE_PATHS
    | {
        ".".join(_normalize_key(part) for part in path.split("."))
        for paths in _UPSTREAM_SENSITIVE_MAP.values()
        for path in paths
    }
)

_SENSITIVE_DOTTED_SUFFIXES: tuple[str, ...] = tuple(
    f".{p}" for p in sorted(_SENSITIVE_FIELD_PATHS)
)

# Leaf keys that are unconditionally sensitive PII, Customer Match identifiers,
# or credentials at any nesting depth. Generic leaf names like "text" (from
# "message_details.text") are excluded here so non-PII fields like
# text_asset.text are not over-redacted; "message_details.text" is still matched
# via _SENSITIVE_FIELD_PATHS / _SENSITIVE_DOTTED_SUFFIXES.
_SENSITIVE_LEAF_KEYS: frozenset[str] = frozenset(
    {
        path.rsplit(".", maxsplit=1)[-1]
        for path in _SENSITIVE_FIELD_PATHS
        if path.rsplit(".", maxsplit=1)[-1] != "text"
    }
    | {
        # Broader Google Ads / Customer Match / conversion PII fields
        "first_name",
        "last_name",
        "given_name",
        "family_name",
        "street_address",
        "postal_code",
        "hashed_email",
        "hashed_phone_number",
        "hashed_first_name",
        "hashed_last_name",
        "hashed_street_address",
        "mobile_id",
        "third_party_user_id",
        # Credentials, secrets, and auth headers
        "developer_token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "jwt_signing_key",
        "encryption_key",
        "api_key",
        "authorization",
        "cookie",
        "set_cookie",
        "password",
        "secret",
    }
)

# Tool argument keys carrying binary or base64-encoded media payloads.
_BINARY_ARGUMENT_KEYS: frozenset[str] = frozenset(
    {
        "image_asset_data",
        "video_asset_data",
        "media_data",
        "media_bundle_data",
        "file_data",
        "binary_data",
    }
)

# Arguments whose string contents can embed GAQL expressions/predicates.
_GAQL_TEXT_KEYS: frozenset[str] = frozenset(
    {"conditions", "orderings", "resource", "query"}
)

_DATA_URI_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)
_BASE64_BLOB_RE = re.compile(r"[A-Za-z0-9+/=_-]+")
_EMAIL_DOMAIN_RE = re.compile(r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_EMAIL_LOCAL_EXTRA_CHARS = frozenset("._+-")
_HEX_CHECKSUM_RE = re.compile(r"^[0-9a-fA-F]{16,128}$")
_QUOTED_LITERAL_RE = re.compile(
    r"'([^'\\]*(?:\\.[^'\\]*)*)'|\"([^\"\\]*(?:\\.[^\"\\]*)*)\""
)
_SENSITIVE_GAQL_FIELD_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(token)
        for token in sorted(
            _SENSITIVE_FIELD_PATHS | _SENSITIVE_LEAF_KEYS,
            key=len,
            reverse=True,
        )
    )
    + r")\b",
    re.IGNORECASE,
)


def _is_email_local_char(ch: str) -> bool:
    return ch.isalnum() or ch in _EMAIL_LOCAL_EXTRA_CHARS


def _redact_emails(text: str) -> str:
    """Replaces email addresses in linear O(N) time without regex backtracking."""
    if "@" not in text:
        return text

    parts: list[str] = []
    cursor = 0
    for match in _EMAIL_DOMAIN_RE.finditer(text):
        at_idx = match.start()
        if at_idx < cursor:
            continue
        local_start = at_idx
        while local_start > cursor and _is_email_local_char(
            text[local_start - 1]
        ):
            local_start -= 1
        if local_start == at_idx:
            continue
        parts.append(text[cursor:local_start])
        parts.append(REDACTED_MASK)
        cursor = match.end()

    if cursor == 0:
        return text
    parts.append(text[cursor:])
    return "".join(parts)


def _truncate_and_redact_string(text: str) -> str:
    """Redacts emails and truncates oversized strings without splitting emails at the boundary."""
    orig_len = len(text)
    if orig_len <= _MAX_STRING_LENGTH:
        return _redact_emails(text)

    window = text[: _MAX_STRING_LENGTH + _EMAIL_SCAN_LOOKAHEAD]
    redacted_window = _redact_emails(window)
    clipped = redacted_window[:_MAX_STRING_LENGTH]
    omitted = orig_len - _MAX_STRING_LENGTH
    return f"{clipped}...[truncated {omitted} chars]"


def _is_sensitive_path(norm_path: str, norm_key: str) -> bool:
    """Returns True if the normalized key or dotted path matches a sensitive PII/credential field."""
    if norm_key in _SENSITIVE_LEAF_KEYS:
        return True
    return norm_path in _SENSITIVE_FIELD_PATHS or norm_path.endswith(
        _SENSITIVE_DOTTED_SUFFIXES
    )


def redact_gaql_text(text: str) -> str:
    """Redacts sensitive field literals and email addresses inside a GAQL string or fragment."""
    orig_len = len(text)
    working = (
        text
        if orig_len <= _MAX_STRING_LENGTH
        else text[: _MAX_STRING_LENGTH + _EMAIL_SCAN_LOOKAHEAD]
    )
    if _SENSITIVE_GAQL_FIELD_RE.search(working):
        working = _QUOTED_LITERAL_RE.sub(
            lambda m: (
                f"'{REDACTED_MASK}'"
                if m.group(0).startswith("'")
                else f'"{REDACTED_MASK}"'
            ),
            working,
        )
    working = _redact_emails(working)
    if orig_len > _MAX_STRING_LENGTH:
        omitted = orig_len - _MAX_STRING_LENGTH
        return f"{working[:_MAX_STRING_LENGTH]}...[truncated {omitted} chars]"
    return working


def _redact_value(value: Any, norm_path: str = "", norm_key: str = "") -> Any:
    """Recursively redacts binary payloads and PII fields from a tool argument value."""
    if norm_key in _BINARY_ARGUMENT_KEYS and value is not None:
        return REDACTED_MASK

    # Protobuf bytes fields in sub-messages (e.g. ImageAsset.data, MediaBundleAsset.data)
    # are passed via extra_params as {"data": "<base64>"}.
    if norm_key == "data" and "." in norm_path and value is not None:
        return REDACTED_MASK

    if _is_sensitive_path(norm_path, norm_key) and value is not None:
        return REDACTED_MASK

    if isinstance(value, (bytes, bytearray, memoryview)):
        return REDACTED_MASK

    if isinstance(value, (proto.Message, PbMessage)):
        masked_msg = value
        if callable(_mask_proto_message):
            with contextlib.suppress(Exception):
                masked_msg = _mask_proto_message(value, REDACTED_MASK)
        as_dict = utils.format_output_value(masked_msg)
        return _redact_value(as_dict, norm_path=norm_path, norm_key=norm_key)

    if isinstance(value, Mapping):
        # Redact {"key": "<sensitive>", "value": "<secret>"} pairs (e.g. url_custom_parameters).
        raw_param_key = value.get("key")
        force_redact_param_val = isinstance(
            raw_param_key, str
        ) and _is_sensitive_path(
            _normalize_key(raw_param_key), _normalize_key(raw_param_key)
        )
        result: dict[str, Any] = {}
        for k, v in value.items():
            k_str = str(k)
            child_norm_key = _normalize_key(k_str)
            child_norm_path = (
                f"{norm_path}.{child_norm_key}" if norm_path else child_norm_key
            )
            if force_redact_param_val and k_str == "value" and v is not None:
                result[k_str] = REDACTED_MASK
            else:
                result[k_str] = _redact_value(
                    v, norm_path=child_norm_path, norm_key=child_norm_key
                )
        return result

    if isinstance(value, (list, tuple)):
        return [
            _redact_value(item, norm_path=norm_path, norm_key=norm_key)
            for item in value
        ]

    if isinstance(value, AbstractSet):
        redacted_items = [
            _redact_value(item, norm_path=norm_path, norm_key=norm_key)
            for item in value
        ]
        return sorted(redacted_items, key=str)

    if isinstance(value, str):
        if _DATA_URI_RE.match(value):
            return REDACTED_MASK
        if (
            len(value) > _MIN_BASE64_REDACT_LEN
            and _BASE64_BLOB_RE.fullmatch(value) is not None
        ):
            return REDACTED_MASK
        if norm_key in _GAQL_TEXT_KEYS:
            return redact_gaql_text(value)
        return _truncate_and_redact_string(value)

    return value


def redact_arguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Returns a new dict of tool arguments with binary payloads and PII replaced by 'REDACTED'."""
    if not arguments:
        return {}
    return _redact_value(arguments)


def _sanitize_checksum(raw_checksum: Any) -> str | None:
    """Returns a normalized lowercase hex checksum, 'INVALID' if malformed, or None if absent."""
    if raw_checksum is None:
        return None
    if isinstance(raw_checksum, str):
        stripped = raw_checksum.strip()
        if not stripped:
            return None
        if _HEX_CHECKSUM_RE.fullmatch(stripped):
            return stripped.lower()
    return "INVALID"


def _extract_issued_checksum(result: Any) -> str | None:
    """Extracts the issued SHA-256 checksum from a PROPOSE JSON response, if present."""
    candidate_text: str | None = None
    if isinstance(result, str):
        candidate_text = result
    elif isinstance(result, ToolResult):
        for block in result.content or ():
            text = getattr(block, "text", None)
            if isinstance(text, str):
                candidate_text = text
                break
        if candidate_text is None and isinstance(
            result.structured_content, Mapping
        ):
            inner = result.structured_content.get("result")
            if isinstance(inner, str):
                candidate_text = inner

    if not candidate_text or '"checksum"' not in candidate_text:
        return None
    try:
        parsed = json.loads(candidate_text)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, Mapping) and parsed.get("status") == "PROPOSED":
        sanitized = _sanitize_checksum(parsed.get("checksum"))
        if sanitized and sanitized != "INVALID":
            return sanitized
    return None


def _call_id(context: MiddlewareContext[Any] | None) -> str:
    """Returns the MCP request ID or a fallback ID when no stream is active."""
    if context is not None:
        ctx = context.fastmcp_context
        if ctx is not None and ctx.request_context is not None:
            return str(ctx.request_id)
    return f"nostream-{uuid.uuid4().hex[:12]}"


def _schema_hash(arguments: Mapping[str, Any] | None) -> str:
    """Computes a structural hash of argument names and value types."""
    if not arguments:
        return "empty"
    shape = sorted(f"{k}:{type(v).__name__}" for k, v in arguments.items())
    return hashlib.sha256("|".join(shape).encode()).hexdigest()[:12]


def _extract_actor(
    context: MiddlewareContext[Any] | None = None,
    *,
    fallback_session_id: str | None = None,
) -> dict[str, Any]:
    """Extracts opaque caller identity ('who') without recording raw PII."""
    actor: dict[str, Any] = {}

    token_obj = None
    with contextlib.suppress(TypeError, LookupError, RuntimeError):
        token_obj = get_access_token()

    if token_obj is not None:
        actor["auth_mode"] = "oauth"
        claims = getattr(token_obj, "claims", None) or {}
        sub = claims.get("sub") or getattr(token_obj, "subject", None)
        sub_str = str(sub) if sub else None
        if sub_str:
            actor["sub"] = sub_str

        # GoogleTokenVerifier sets AccessToken.client_id = sub while placing the
        # OAuth 2.0 client ID in claims["aud"]. Prefer a distinct client_id when
        # present (DCR/CIMD/ID-JAG), falling back to claims["aud"] instead of
        # duplicating sub.
        raw_client_id = getattr(token_obj, "client_id", None)
        aud = claims.get("aud")
        resolved_client_id: str | None = None
        if raw_client_id and str(raw_client_id) != sub_str:
            resolved_client_id = str(raw_client_id)
        elif isinstance(aud, str) and aud:
            resolved_client_id = aud
        elif isinstance(aud, list) and aud:
            resolved_client_id = str(aud[0])
        elif raw_client_id:
            resolved_client_id = str(raw_client_id)
        if resolved_client_id:
            actor["client_id"] = resolved_client_id

        scopes = getattr(token_obj, "scopes", None)
        if scopes:
            actor["scopes"] = list(scopes)
    else:
        actor["auth_mode"] = "adc"

    ctx = context.fastmcp_context if context is not None else None
    session_id: str | None = None
    if ctx is not None:
        with contextlib.suppress(RuntimeError):
            if ctx.session_id:
                session_id = str(ctx.session_id)

        with contextlib.suppress(RuntimeError):
            if ctx.request_context is not None and ctx.session is not None:
                client_params = getattr(ctx.session, "client_params", None)
                # MCP Python SDK v2 uses snake_case client_info (JSON alias clientInfo).
                client_info = getattr(
                    client_params, "client_info", None
                ) or getattr(client_params, "clientInfo", None)
                if client_info is not None:
                    info: dict[str, str] = {}
                    if getattr(client_info, "name", None):
                        info["name"] = str(client_info.name)
                    if getattr(client_info, "version", None):
                        info["version"] = str(client_info.version)
                    if info:
                        actor["client_info"] = info

    if session_id is None and fallback_session_id:
        session_id = str(fallback_session_id)
    if session_id:
        actor["session_id"] = session_id

    return actor


async def _resolve_tool(
    context: MiddlewareContext[Any],
    tool_name: str,
    fallback_server: FastMCP | None = None,
) -> Tool | None:
    """Resolves the target FastMCP Tool for annotation and parameter inspection."""
    ctx = context.fastmcp_context
    server = getattr(ctx, "fastmcp", None) if ctx is not None else None
    if server is None:
        server = fallback_server
    if server is None or not inspect.iscoroutinefunction(
        getattr(server, "get_tool", None)
    ):
        return None
    with contextlib.suppress(FastMCPError):
        return await server.get_tool(tool_name)
    return None


def _is_read_only_tool(tool: Tool | None) -> bool | None:
    """Returns True for read-only tools, False for mutating tools, None if unknown tool."""
    if tool is None:
        return None
    annotations = getattr(tool, "annotations", None)
    read_only_hint = (
        getattr(annotations, "read_only_hint", None)
        if annotations is not None
        else None
    )
    # Per MCP ToolAnnotations spec, missing readOnlyHint defaults to False (potentially mutating).
    if read_only_hint is None:
        return False
    return bool(read_only_hint)


def _coerce_validate_only(raw_value: Any) -> bool:
    """Coerces validate_only using Pydantic's boolean rules so 'false'/0 cannot bypass COMMIT logging."""
    if isinstance(raw_value, bool):
        return raw_value
    try:
        return _BOOL_ADAPTER.validate_python(raw_value)
    except PydanticValidationError:
        # Unparseable values will be rejected by FastMCP input validation before running.
        return True


def _phase_for_tool(
    read_only: bool | None,
    arguments: Mapping[str, Any],
) -> MutationPhase:
    """Determines READ, PROPOSE, or COMMIT from the tool's readOnlyHint and coerced validate_only."""
    if read_only is None or read_only is True:
        return MutationPhase.READ
    if "validate_only" in arguments:
        return (
            MutationPhase.PROPOSE
            if _coerce_validate_only(arguments["validate_only"])
            else MutationPhase.COMMIT
        )
    return MutationPhase.PROPOSE


def _resolve_login_customer_id(
    raw_arguments: Mapping[str, Any],
    tool: Tool | None,
    *,
    accepts_login_customer_id: bool | None = None,
) -> str | None:
    """Resolves login_customer_id only when passed or accepted by the target tool."""
    if "login_customer_id" in raw_arguments:
        return utils.get_login_customer_id(
            raw_arguments.get("login_customer_id")
        )
    if accepts_login_customer_id is None and tool is not None:
        props = (getattr(tool, "parameters", None) or {}).get("properties", {})
        accepts_login_customer_id = "login_customer_id" in props
    if accepts_login_customer_id:
        return utils.get_login_customer_id(None)
    return None


def _classify_exception(
    exc: Exception, tool_name: str
) -> tuple[AuditStatus, str]:
    """Classifies a raised exception into (status, error_type_name)."""
    if isinstance(exc, (ValidationError, NotFoundError, DisabledError)):
        return AuditStatus.ERROR, type(exc).__name__

    if isinstance(exc, ToolError):
        cause = exc.__cause__
        # FastMCP.call_tool wraps unhandled crashes as `ToolError("Error calling tool ...") from e`.
        if (
            cause is not None
            and not isinstance(cause, (FastMCPError, GoogleAdsException))
            and str(exc).startswith(f"Error calling tool {tool_name!r}")
        ):
            return AuditStatus.FAILED, type(cause).__name__
        if isinstance(cause, GoogleAdsException):
            return AuditStatus.ERROR, type(cause).__name__
        return AuditStatus.ERROR, type(exc).__name__

    return AuditStatus.FAILED, type(exc).__name__


def _is_empty_result(result: Any) -> bool:
    """Returns True when a ToolResult (or raw return value) carries no data."""
    if result is None or result == [] or result == "":
        return True
    if isinstance(result, ToolResult):
        content = result.content
        structured = result.structured_content
        if not content:
            if not structured:
                return True
            # FastMCP wraps empty annotated list returns (e.g. search() -> []) as {"result": []}.
            if structured == {"result": []}:
                return True
        return False
    return False


_ORIG_FN_ATTR = "_ads_mcp_audit_original_fn"


class AuditMiddleware(Middleware):
    """FastMCP middleware that emits structured audit records for every tool call."""

    def __init__(
        self,
        storage: AsyncKeyValue | None = None,
        collection: str = AUDIT_COLLECTION,
        *,
        ttl: float | None = None,
        server: FastMCP | None = None,
    ) -> None:
        super().__init__()
        self.storage = storage
        self.collection = collection
        self.ttl = ttl
        self._fallback_server = server

    def instrument_server(
        self,
        server: FastMCP,
        *,
        namespace: str | None = None,
    ) -> None:
        """Wraps task-enabled FunctionTools on ``server`` so background Docket worker runs are audited.

        Foreground calls pass straight through (audited by ``on_call_tool``).
        Background executions inside a Docket worker emit a ``task_execution``
        audit record capturing completion status, duration, and errors.
        """
        self._fallback_server = self._fallback_server or server
        local_provider = getattr(server, "local_provider", None)
        components = getattr(local_provider, "_components", None)
        if not isinstance(components, Mapping):
            return

        for comp in components.values():
            if (
                isinstance(comp, FunctionTool)
                and comp.task_config.supports_tasks()
            ):
                self._wrap_task_function_tool(comp, namespace=namespace)

    def _wrap_task_function_tool(
        self,
        tool: FunctionTool,
        *,
        namespace: str | None = None,
    ) -> None:
        orig_fn = getattr(tool.fn, _ORIG_FN_ATTR, tool.fn)
        sig = inspect.signature(orig_fn)
        is_coro = inspect.iscoroutinefunction(orig_fn)
        accepts_login_cid = "login_customer_id" in sig.parameters
        read_only = _is_read_only_tool(tool)
        default_name = f"{namespace}_{tool.name}" if namespace else tool.name
        middleware = self

        async def _run_audited_in_worker(*args: Any, **kwargs: Any) -> Any:
            from fastmcp_tasks.context import (
                _recall_snapshot,
                get_task_context,
                get_task_session_id,
            )

            task_info = get_task_context()
            if task_info is None:
                if is_coro:
                    return await orig_fn(*args, **kwargs)
                return orig_fn(*args, **kwargs)

            start = time.perf_counter()
            received_at = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            bound = sig.bind_partial(*args, **kwargs)
            raw_arguments = dict(bound.arguments)
            bound.apply_defaults()

            snapshot = _recall_snapshot(task_info.task_id)
            tool_name = (
                getattr(snapshot, "owning_tool_name", None) or default_name
            )
            origin_req_id = getattr(snapshot, "origin_request_id", None)
            call_id = (
                str(origin_req_id)
                if origin_req_id is not None
                else f"task-{task_info.task_id[:12]}"
            )

            raw_customer_id = raw_arguments.get("customer_id")
            customer_id = (
                utils.clean_customer_id(raw_customer_id) or None
                if raw_customer_id is not None
                else None
            )
            phase = _phase_for_tool(read_only, raw_arguments)

            record: dict[str, Any] = {
                "event": "task_execution",
                "audit_id": uuid.uuid4().hex,
                "tool": tool_name,
                "call_id": call_id,
                "task_id": task_info.task_id,
                "received_at": received_at,
                "actor": _extract_actor(
                    None, fallback_session_id=get_task_session_id()
                ),
                "customer_id": customer_id,
                "login_customer_id": _resolve_login_customer_id(
                    raw_arguments,
                    tool,
                    accepts_login_customer_id=accepts_login_cid,
                ),
                "mutation_phase": str(phase),
                "checksum": _sanitize_checksum(raw_arguments.get("checksum")),
                "schema_hash": _schema_hash(raw_arguments),
                "arguments": redact_arguments(raw_arguments),
            }

            try:
                out = (
                    await orig_fn(*args, **kwargs)
                    if is_coro
                    else orig_fn(*args, **kwargs)
                )
            except Exception as exc:
                status, err_name = _classify_exception(exc, tool_name)
                record["status"] = str(status)
                record["error"] = err_name
                record["duration_ms"] = round(
                    (time.perf_counter() - start) * 1000, 2
                )
                await middleware.emit(record)
                raise

            if phase is MutationPhase.PROPOSE:
                issued = _extract_issued_checksum(out)
                if issued:
                    record["checksum"] = issued

            record["status"] = str(
                AuditStatus.EMPTY
                if _is_empty_result(out)
                else AuditStatus.COMPLETED
            )
            record["duration_ms"] = round(
                (time.perf_counter() - start) * 1000, 2
            )
            await middleware.emit(record)
            return out

        functools.update_wrapper(_run_audited_in_worker, orig_fn)
        _run_audited_in_worker.__signature__ = sig  # type: ignore[attr-defined]
        setattr(_run_audited_in_worker, _ORIG_FN_ATTR, orig_fn)
        tool.fn = _run_audited_in_worker

    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp_types.CallToolRequestParams],
        call_next: CallNext[mcp_types.CallToolRequestParams, Any],
    ) -> Any:
        start = time.perf_counter()
        raw_arguments: Mapping[str, Any] = context.message.arguments or {}
        tool_name = context.message.name

        tool = await _resolve_tool(context, tool_name, self._fallback_server)
        read_only = _is_read_only_tool(tool)
        phase = _phase_for_tool(read_only, raw_arguments)

        raw_customer_id = raw_arguments.get("customer_id")
        customer_id = (
            utils.clean_customer_id(raw_customer_id) or None
            if raw_customer_id is not None
            else None
        )

        record: dict[str, Any] = {
            "event": "tool_call",
            "audit_id": uuid.uuid4().hex,
            "tool": tool_name,
            "call_id": _call_id(context),
            "received_at": context.timestamp.isoformat(),
            "actor": _extract_actor(context),
            "customer_id": customer_id,
            "login_customer_id": _resolve_login_customer_id(
                raw_arguments, tool
            ),
            "mutation_phase": str(phase),
            "checksum": _sanitize_checksum(raw_arguments.get("checksum")),
            "schema_hash": _schema_hash(raw_arguments),
            "arguments": redact_arguments(raw_arguments),
        }

        try:
            result = await call_next(context)
        except Exception as exc:
            status, err_name = _classify_exception(exc, tool_name)
            record["status"] = str(status)
            record["error"] = err_name
            record["duration_ms"] = round(
                (time.perf_counter() - start) * 1000, 2
            )
            await self.emit(record)
            raise

        task_id = (
            getattr(result, "task_id", None)
            if not isinstance(result, ToolResult)
            else None
        )
        if task_id is not None:
            record["status"] = str(AuditStatus.ENQUEUED)
            record["task_id"] = str(task_id)
        elif getattr(result, "is_error", False):
            record["status"] = str(AuditStatus.ERROR)
        elif _is_empty_result(result):
            record["status"] = str(AuditStatus.EMPTY)
        else:
            record["status"] = str(AuditStatus.COMPLETED)
            if phase is MutationPhase.PROPOSE:
                issued = _extract_issued_checksum(result)
                if issued:
                    record["checksum"] = issued

        record["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        await self.emit(record)
        return result

    async def emit(self, record: dict[str, Any]) -> None:
        """Logs the audit record as structured JSON and persists it if storage is configured."""
        audit_logger.info(json.dumps(record, sort_keys=True, default=str))
        if self.storage is not None:
            unique_suffix = record.get("audit_id") or record.get("call_id")
            key = f"{record['received_at']}_{unique_suffix}"
            put_kwargs: dict[str, Any] = {
                "key": key,
                "value": record,
                "collection": self.collection,
            }
            if self.ttl is not None:
                put_kwargs["ttl"] = self.ttl
            try:
                await self.storage.put(**put_kwargs)
            except Exception as exc:
                _storage_logger.error(
                    "Failed to persist audit record %s to storage: %s",
                    key,
                    exc,
                )
