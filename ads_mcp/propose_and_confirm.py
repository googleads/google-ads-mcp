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

"""Generalized propose-and-confirm workflow utilities for MCP mutate tools."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import json
import logging
import struct
from typing import Any

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.message import Message as PbMessage
import proto

from ads_mcp import utils

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChangeItem:
    """A single structured before/after change item for user review and confirmation."""

    operation: str
    entity_readable: str
    primary_key_readable: str = ""
    field_readable: str = ""
    value_readable: str = ""
    original_value_readable: str = ""

    def to_dict(self) -> dict[str, str]:
        """Converts the ChangeItem into a dictionary representation."""
        result: dict[str, str] = {
            "operation": self.operation,
            "entity_readable": self.entity_readable,
            "primary_key_readable": self.primary_key_readable,
            "field_readable": self.field_readable,
            "value_readable": self.value_readable,
        }
        if self.original_value_readable:
            result["original_value_readable"] = self.original_value_readable
        return result


def _format_readable_value(value: Any) -> str:
    """Formats a field value into a human-readable string for ChangeItem display."""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def build_change_items(
    operation: str,
    entity_readable: str,
    primary_key_readable: str,
    fields: Mapping[str, Any],
    original_fields: Mapping[str, Any] | None = None,
) -> list[ChangeItem]:
    """Builds a list of ChangeItems from a mapping of field labels to proposed values.

    Args:
        operation: The operation type (e.g., 'CREATE', 'UPDATE', 'REMOVE').
        entity_readable: Human-readable entity name (e.g., 'Asset (TEXT)', 'Label').
        primary_key_readable: Human-readable identifier of the target resource.
        fields: Mapping of human-readable field names to proposed values.
            Entries with None values are skipped.
        original_fields: Optional mapping of field names to original values
            prior to mutation (for UPDATE/REMOVE operations).

    Returns:
        A list of ChangeItem instances describing the proposed changes.
    """
    items: list[ChangeItem] = []
    orig_map = original_fields or {}
    for field_name, value in fields.items():
        if value is None:
            continue
        orig_val = orig_map.get(field_name)
        items.append(
            ChangeItem(
                operation=operation,
                entity_readable=entity_readable,
                primary_key_readable=primary_key_readable,
                field_readable=field_name,
                value_readable=_format_readable_value(value),
                original_value_readable=(
                    _format_readable_value(orig_val)
                    if orig_val is not None
                    else ""
                ),
            )
        )
    return items


def _normalize_for_checksum(value: Any) -> Any:
    """Recursively normalizes a Python or protobuf value into a canonical JSON structure."""
    if isinstance(value, proto.Message):
        pb_bytes = type(value).pb(value).SerializeToString(deterministic=True)
        return {"__proto__": pb_bytes.hex()}
    if isinstance(value, PbMessage):
        pb_bytes = value.SerializeToString(deterministic=True)
        return {"__proto__": pb_bytes.hex()}
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(k): _normalize_for_checksum(v)
            for k, v in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_checksum(v) for v in value]
    if isinstance(value, set):
        normalized_items = [_normalize_for_checksum(v) for v in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":")
            ),
        )
    return value


def _serialize_operation_for_checksum(operation: Any) -> bytes:
    """Deterministically serializes a single operation for checksum calculation."""
    if isinstance(operation, proto.Message):
        return (
            type(operation).pb(operation).SerializeToString(deterministic=True)
        )
    if isinstance(operation, PbMessage):
        return operation.SerializeToString(deterministic=True)
    normalized = _normalize_for_checksum(operation)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _update_length_prefixed(digest: "hashlib._Hash", chunk: bytes) -> None:
    """Updates a hash digest with an 8-byte big-endian length prefix followed by chunk."""
    digest.update(struct.pack(">Q", len(chunk)))
    digest.update(chunk)


def compute_checksum(customer_id: str, operations: Any) -> str:
    """Computes a deterministic SHA-256 hex digest bound to customer_id and operations.

    Args:
        customer_id: The Google Ads customer ID.
        operations: A single operation payload (dict or proto Message) or a
            sequence of operation payloads.

    Returns:
        A 64-character lowercase hexadecimal SHA-256 checksum string.
    """
    digest = hashlib.sha256()
    _update_length_prefixed(digest, str(customer_id).encode("utf-8"))

    op_list: Sequence[Any]
    if isinstance(operations, (list, tuple)):
        op_list = operations
    else:
        op_list = [operations]

    digest.update(struct.pack(">Q", len(op_list)))
    for op in op_list:
        _update_length_prefixed(digest, _serialize_operation_for_checksum(op))

    return digest.hexdigest()


def verify_checksum(
    customer_id: str,
    operations: Any,
    checksum: str | None,
    expected_checksum: str | None = None,
) -> str | None:
    """Verifies that a non-blank checksum matches the expected checksum for the operation.

    Args:
        customer_id: The Google Ads customer ID.
        operations: The operation payload(s) to verify against.
        checksum: The checksum provided by the caller.
        expected_checksum: Optional precomputed expected checksum.

    Returns:
        None if the checksum is valid, or an actionable error message string if
        missing or mismatched.
    """
    if not checksum or not checksum.strip():
        return (
            "Error: checksum from a previous validate_only=True call is "
            "required when validate_only=False."
        )

    actual_expected = (
        expected_checksum.lower()
        if expected_checksum is not None
        else compute_checksum(customer_id, operations)
    )
    provided_bytes = checksum.strip().lower().encode("utf-8")
    expected_bytes = actual_expected.encode("utf-8")

    if not hmac.compare_digest(provided_bytes, expected_bytes):
        return (
            f"Error: Invalid or mismatched checksum for customer_id "
            f"'{customer_id}' and operation parameters. Please call the tool "
            f"with validate_only=True first to obtain a valid checksum."
        )

    return None


def format_proposal_response(
    customer_id: str,
    checksum: str,
    change_items: Sequence[ChangeItem],
) -> str:
    """Formats a structured JSON response for a validated mutation proposal."""
    payload = {
        "status": "PROPOSED",
        "validate_only": True,
        "customer_id": customer_id,
        "checksum": checksum,
        "change_items": [item.to_dict() for item in change_items],
        "message": (
            "Validation succeeded (validate_only=True). No changes have been "
            "committed. Present the proposed change_items to the user and "
            "wait for explicit user confirmation, then call this tool again "
            "with validate_only=False, the exact same parameters, and the "
            "returned checksum."
        ),
    }
    return json.dumps(payload, indent=2)


def _format_exception(error_prefix: str, exc: Exception) -> str:
    """Formats GoogleAdsException or generic Exception with error_prefix."""
    if isinstance(exc, GoogleAdsException):
        return f"{error_prefix}:\n{utils.format_google_ads_error(exc)}"
    return f"{error_prefix}: {exc}"


def propose_and_confirm(
    *,
    customer_id: str,
    validate_only: bool,
    checksum: str | None,
    operation_payload: Any,
    change_items: Sequence[ChangeItem],
    validate_fn: Callable[[], Any] | None = None,
    commit_fn: Callable[[], str],
    error_prefix: str = "Failed to execute mutation",
) -> str:
    """Executes the generalized two-phase propose-and-confirm mutation workflow.

    - Given ``validate_only=True`` (Propose / Validate):
      1. Runs ``validate_fn()`` if provided (e.g. calling the Google Ads API
         service with ``validate_only=True``). If validation raises an exception,
         the proposal is rejected and no checksum is issued.
      2. Computes the deterministic SHA-256 ``checksum`` bound to ``customer_id``
         and ``operation_payload``.
      3. Returns a structured JSON proposal with ``change_items`` and ``checksum``.

    - Given ``validate_only=False`` (Confirm / Commit):
      1. Requires ``checksum`` from a prior ``validate_only=True`` call and
         verifies it matches ``customer_id`` and ``operation_payload`` in
         constant time before executing any mutation.
      2. Calls ``commit_fn()`` to commit the mutation and returns its result.
    """
    expected_checksum = compute_checksum(customer_id, operation_payload)

    if validate_only:
        if validate_fn is not None:
            try:
                validate_fn()
            except ToolError:
                raise
            except Exception as exc:
                msg = _format_exception(error_prefix, exc)
                logger.error("%s", msg)
                raise ToolError(msg) from exc
        return format_proposal_response(
            customer_id=customer_id,
            checksum=expected_checksum,
            change_items=change_items,
        )

    checksum_err = verify_checksum(
        customer_id=customer_id,
        operations=operation_payload,
        checksum=checksum,
        expected_checksum=expected_checksum,
    )
    if checksum_err:
        raise ToolError(checksum_err)

    try:
        return commit_fn()
    except ToolError:
        raise
    except Exception as exc:
        msg = _format_exception(error_prefix, exc)
        logger.error("%s", msg)
        raise ToolError(msg) from exc
