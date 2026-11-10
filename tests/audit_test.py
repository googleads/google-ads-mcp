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

"""Tests for MCP tool call audit middleware, redaction, tasks, and storage."""

from __future__ import annotations

import datetime
import os
import shutil
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.base import ToolResult
from fastmcp_tasks import TasksExtension
from fastmcp_tasks.client import TasksClientExtension, call_tool_task
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.resources.types.customer_user_access import (
    CustomerUserAccess,
)
from google.auth.credentials import AnonymousCredentials
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper
from mcp import types as mcp_types

from ads_mcp import propose_and_confirm as pac
from ads_mcp.audit import (
    AUDIT_COLLECTION,
    AuditMiddleware,
    AuditStatus,
    MutationPhase,
    REDACTED_MASK,
    redact_arguments,
    redact_gaql_text,
)
from ads_mcp.auth_storage import (
    create_audit_storage,
    create_client_storage,
    get_audit_storage_ttl,
)
from ads_mcp.tools import search as search_tool_mod


class RedactArgumentsTest(unittest.TestCase):
    """Tests for PII, credential, and binary argument redaction."""

    def test_redact_binary_and_base64_arguments(self):
        """Binary, data URIs, nested 'data', and large base64 blobs are replaced with REDACTED."""
        large_b64 = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=" * 20  # > 512 chars
        args = {
            "customer_id": "123-456-7890",
            "asset_name": "Hero Banner",
            "asset_type": "MEDIA_BUNDLE",
            "image_asset_data": "iVBORw0KGgoAAAANSUhEUgAAAAUA",
            "imageAssetData": "iVBORw0KGgoAAAANSUhEUgAAAAUA",
            "video_asset_data": "AAAAIGZ0eXBpc29t",
            "raw_bytes": b"\x89PNG\r\n\x1a\n",
            "raw_bytearray": bytearray(b"binary-content"),
            "raw_memview": memoryview(b"binary-view"),
            "data_uri": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
            "extra_params": {"data": "UEsDBBQAAAAIA..."},
            "unlabeled_blob": large_b64,
        }
        redacted = redact_arguments(args)
        self.assertEqual(redacted["customer_id"], "123-456-7890")
        self.assertEqual(redacted["asset_name"], "Hero Banner")
        self.assertEqual(redacted["asset_type"], "MEDIA_BUNDLE")
        for key in (
            "image_asset_data",
            "imageAssetData",
            "video_asset_data",
            "raw_bytes",
            "raw_bytearray",
            "raw_memview",
            "data_uri",
            "unlabeled_blob",
        ):
            self.assertEqual(redacted[key], REDACTED_MASK, key)
        self.assertEqual(redacted["extra_params"]["data"], REDACTED_MASK)

    def test_redact_sensitive_snake_and_camel_case_fields(self):
        """Sensitive Google Ads and Customer Match fields are redacted in both snake_case and camelCase."""
        args = {
            "customer_id": "1234567890",
            "email_address": "alice@example.com",
            "inviter_user_email_address": "admin@example.com",
            "user_email": "bob@example.com",
            "request_user_email": "reviewer@example.com",
            "extra_params": {
                "contact_details": {
                    "phone_number": "+15551234567",
                    "phone_number_extension": "101",
                    "email": "lead@example.com",
                    "consumer_name": "Jane Doe",
                },
                "contactDetails": {
                    "phoneNumber": "+15559876543",
                    "consumerName": "John Roe",
                },
                "placesLocationFeedData": {
                    "emailAddress": "places@example.com",
                },
                "messageDetails": {
                    "text": "Private customer lead conversation message",
                },
                "addressInfo": {
                    "firstName": "Alice",
                    "lastName": "Smith",
                    "streetAddress": "742 Evergreen Terrace",
                    "postalCode": "90210",
                    "hashedEmail": "abc123hash",
                },
                "text_asset": {
                    "text": "Non-sensitive ad headline text",
                },
            },
            "text_asset_text": "Public ad copy.",
            "notes": "Contact support@example.com.",
            "tag_set": {"secret@example.com", "public-tag"},
        }
        redacted = redact_arguments(args)
        self.assertEqual(redacted["email_address"], REDACTED_MASK)
        self.assertEqual(redacted["inviter_user_email_address"], REDACTED_MASK)
        self.assertEqual(redacted["user_email"], REDACTED_MASK)
        self.assertEqual(redacted["request_user_email"], REDACTED_MASK)

        extra = redacted["extra_params"]
        for field in (
            "phone_number",
            "phone_number_extension",
            "email",
            "consumer_name",
        ):
            self.assertEqual(extra["contact_details"][field], REDACTED_MASK)
        self.assertEqual(extra["contactDetails"]["phoneNumber"], REDACTED_MASK)
        self.assertEqual(extra["contactDetails"]["consumerName"], REDACTED_MASK)
        self.assertEqual(
            extra["placesLocationFeedData"]["emailAddress"], REDACTED_MASK
        )
        self.assertEqual(extra["messageDetails"]["text"], REDACTED_MASK)
        for field in (
            "firstName",
            "lastName",
            "streetAddress",
            "postalCode",
            "hashedEmail",
        ):
            self.assertEqual(extra["addressInfo"][field], REDACTED_MASK)

        # Non-sensitive "text" fields and trailing punctuation are preserved
        self.assertEqual(
            extra["text_asset"]["text"], "Non-sensitive ad headline text"
        )
        self.assertEqual(redacted["text_asset_text"], "Public ad copy.")
        self.assertEqual(redacted["notes"], f"Contact {REDACTED_MASK}.")
        self.assertEqual(redacted["tag_set"], [REDACTED_MASK, "public-tag"])

    def test_redact_proto_message_with_sensitive_fields(self):
        """Proto-plus messages passed in arguments are masked via mask_message."""
        access_msg = CustomerUserAccess(
            resource_name="customers/123/customerUserAccesses/456",
            email_address="secret@example.com",
            inviter_user_email_address="inviter@example.com",
        )
        redacted = redact_arguments({"access": access_msg})
        self.assertEqual(
            redacted["access"]["resource_name"],
            "customers/123/customerUserAccesses/456",
        )
        self.assertEqual(redacted["access"]["email_address"], REDACTED_MASK)
        self.assertEqual(
            redacted["access"]["inviter_user_email_address"], REDACTED_MASK
        )

    def test_redact_credentials_and_url_custom_parameters(self):
        """Credential keys and sensitive key-value custom parameters are redacted."""
        args = {
            "developer_token": "dev-tok-123",
            "developerToken": "dev-tok-camel",
            "access_token": "ya29.secret",
            "refresh_token": "1//refresh",
            "clientSecret": "GOCSPX-secret",
            "authorization": "Bearer ya29.secret",
            "url_custom_parameters": [
                {"key": "access_token", "value": "secret-tok"},
                {"key": "utm_campaign", "value": "spring_sale"},
            ],
        }
        redacted = redact_arguments(args)
        for key in (
            "developer_token",
            "developerToken",
            "access_token",
            "refresh_token",
            "clientSecret",
            "authorization",
        ):
            self.assertEqual(redacted[key], REDACTED_MASK)
        self.assertEqual(
            redacted["url_custom_parameters"],
            [
                {"key": "access_token", "value": REDACTED_MASK},
                {"key": "utm_campaign", "value": "spring_sale"},
            ],
        )

    def test_redact_gaql_and_search_debug_log(self):
        """GAQL conditions/resource/orderings and search debug logs redact PII literals."""
        args = {
            "customer_id": "1234567890",
            "resource": (
                "local_services_lead WHERE "
                "local_services_lead.contact_details.phone_number = '+15550001111'"
            ),
            "fields": ["customer_user_access.user_id"],
            "conditions": [
                "customer_user_access.email_address = 'alice@example.com'",
                "local_services_lead.contact_details.phone_number = '+15551234567'",
                "local_services_lead.contact_details.consumer_name = 'Jane Doe'",
                "local_services_lead_conversation.message_details.text LIKE '%private%'",
                "campaign.status = 'ENABLED'",
            ],
        }
        redacted = redact_arguments(args)
        self.assertNotIn("+15550001111", redacted["resource"])
        self.assertEqual(
            redacted["conditions"],
            [
                f"customer_user_access.email_address = '{REDACTED_MASK}'",
                f"local_services_lead.contact_details.phone_number = '{REDACTED_MASK}'",
                f"local_services_lead.contact_details.consumer_name = '{REDACTED_MASK}'",
                f"local_services_lead_conversation.message_details.text LIKE '{REDACTED_MASK}'",
                "campaign.status = 'ENABLED'",
            ],
        )

        # Verify search.py debug logs never leak raw GAQL PII
        mock_svc = MagicMock()
        mock_svc.search_stream.return_value = []
        with (
            patch("ads_mcp.utils.get_googleads_service", return_value=mock_svc),
            self.assertLogs("ads_mcp.utils", level="DEBUG") as cm,
        ):
            search_tool_mod.search(
                customer_id="1234567890",
                fields=["customer_user_access.user_id"],
                resource="customer_user_access",
                conditions=[
                    "customer_user_access.email_address = 'leak@example.com'",
                    "local_services_lead.contact_details.phone_number = '+15559998888'",
                ],
            )
        joined_logs = "\n".join(cm.output)
        self.assertNotIn("leak@example.com", joined_logs)
        self.assertNotIn("+15559998888", joined_logs)
        self.assertIn(REDACTED_MASK, joined_logs)

    def test_linear_time_email_redaction_and_boundary_truncation(self):
        """Adversarial long inputs run in milliseconds without ReDoS or boundary leaks."""
        # Pathological non-email string with spaces + trailing '@' without domain dot
        adversarial = ("word " * 20_000) + ("a" * 5_000) + "@nodot"
        start = time.perf_counter()
        result = redact_arguments({"description": adversarial})
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed_ms, 100.0)
        self.assertIn("...[truncated ", result["description"])

        # Email straddling the 4096-character truncation boundary is still redacted
        prefix = "x " * 2045  # 4090 chars
        boundary_email = f"{prefix}secret.user@example.com trailing text"
        redacted_boundary = redact_arguments({"description": boundary_email})[
            "description"
        ]
        self.assertNotIn("secret.user", redacted_boundary)
        self.assertNotIn("example.com", redacted_boundary)
        self.assertEqual(
            redact_gaql_text("customer_user_access.email_address = 'a@b.co'"),
            f"customer_user_access.email_address = '{REDACTED_MASK}'",
        )


class AuditMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    """Unit tests for AuditMiddleware actor extraction, storage keys, TTL, and resilience."""

    def _make_context(
        self,
        name: str = "search_search",
        arguments: dict[str, Any] | None = None,
        fastmcp_context: Any = None,
    ) -> MiddlewareContext[mcp_types.CallToolRequestParams]:
        msg = mcp_types.CallToolRequestParams(
            name=name,
            arguments=arguments,
        )
        return MiddlewareContext(
            message=msg,
            fastmcp_context=fastmcp_context,
            method="tools/call",
            timestamp=datetime.datetime(
                2026, 4, 15, 10, 30, 0, tzinfo=datetime.timezone.utc
            ),
        )

    @patch("ads_mcp.audit.get_access_token")
    async def test_oauth_actor_excludes_pii_and_resolves_google_aud(
        self, mock_get_token
    ):
        """GoogleProvider tokens resolve client_id from claims['aud'] rather than duplicating sub, and omit PII."""
        # Matches GoogleTokenVerifier's real AccessToken shape (client_id == sub, aud == OAuth client).
        mock_get_token.return_value = SimpleNamespace(
            token="ya29.raw-access-token",
            client_id="google-sub-999888",
            subject="google-sub-999888",
            scopes=["openid", "https://www.googleapis.com/auth/adwords"],
            claims={
                "sub": "google-sub-999888",
                "aud": "12345-app.apps.googleusercontent.com",
                "email": "sensitive.user@example.com",
                "name": "Sensitive User Name",
            },
        )
        fake_ctx = MagicMock()
        fake_ctx.fastmcp = None
        fake_ctx.request_context = MagicMock()
        fake_ctx.request_id = "2"
        fake_ctx.session_id = "sess-abc"
        fake_ctx.session.client_params = SimpleNamespace(
            client_info=SimpleNamespace(name="codex-cli", version="0.146.0")
        )

        from ads_mcp.coordinator import mcp as root_mcp

        store = MemoryStore()
        middleware = AuditMiddleware(storage=store, server=root_mcp)
        valid_checksum = "deadbeef" * 8
        context = self._make_context(
            name="assets_create_asset",
            arguments={
                "customer_id": "123-456-7890",
                "login_customer_id": "999-888-7777",
                "name": "Spring Logo",
                "asset_type": "IMAGE",
                "image_asset_data": "base64encodedimagepayload==",
                "validate_only": False,
                "checksum": valid_checksum.upper(),
            },
            fastmcp_context=fake_ctx,
        )

        call_next = AsyncMock(
            return_value=ToolResult(
                content=[
                    mcp_types.TextContent(
                        type="text", text="Successfully created asset"
                    )
                ]
            )
        )

        with self.assertLogs("ads_mcp.audit", level="INFO") as cm:
            # Invoke twice with identical timestamp and JSON-RPC request_id="2"
            # to verify unique audit_id keys prevent storage overwrites.
            await middleware.on_call_tool(context, call_next)
            await middleware.on_call_tool(context, call_next)

        self.assertEqual(len(cm.output), 2)
        for log_line in cm.output:
            self.assertNotIn("sensitive.user@example.com", log_line)
            self.assertNotIn("Sensitive User Name", log_line)
            self.assertNotIn("ya29.raw-access-token", log_line)
            self.assertNotIn("base64encodedimagepayload==", log_line)

        import json

        rec1 = json.loads(cm.output[0].split("INFO:ads_mcp.audit:", 1)[1])
        rec2 = json.loads(cm.output[1].split("INFO:ads_mcp.audit:", 1)[1])
        self.assertNotEqual(rec1["audit_id"], rec2["audit_id"])

        self.assertEqual(rec1["event"], "tool_call")
        self.assertEqual(rec1["tool"], "assets_create_asset")
        self.assertEqual(rec1["call_id"], "2")
        self.assertEqual(rec1["customer_id"], "1234567890")
        self.assertEqual(rec1["login_customer_id"], "9998887777")
        self.assertEqual(rec1["mutation_phase"], MutationPhase.COMMIT)
        self.assertEqual(rec1["checksum"], valid_checksum)
        self.assertEqual(rec1["status"], AuditStatus.COMPLETED)
        self.assertEqual(rec1["arguments"]["image_asset_data"], REDACTED_MASK)
        self.assertEqual(
            rec1["actor"],
            {
                "auth_mode": "oauth",
                "sub": "google-sub-999888",
                "client_id": "12345-app.apps.googleusercontent.com",
                "scopes": [
                    "openid",
                    "https://www.googleapis.com/auth/adwords",
                ],
                "session_id": "sess-abc",
                "client_info": {"name": "codex-cli", "version": "0.146.0"},
            },
        )

        # Both colliding request_ids are preserved independently in KV storage
        for rec in (rec1, rec2):
            key = f"{rec['received_at']}_{rec['audit_id']}"
            self.assertEqual(
                await store.get(key=key, collection=AUDIT_COLLECTION), rec
            )

    @patch("ads_mcp.audit.get_access_token", return_value=None)
    async def test_checksum_sanitizes_non_hex_input_and_forwards_ttl(
        self, _mock_token
    ):
        """Malformed or PII-bearing checksum arguments never leak into top-level record['checksum']."""
        mock_store = MagicMock()
        mock_store.put = AsyncMock()
        middleware = AuditMiddleware(storage=mock_store, ttl=3600.0)
        ctx = self._make_context(
            name="labels_manage_labels",
            arguments={
                "customer_id": "---",
                "checksum": "leak@example.com",
            },
        )
        await middleware.on_call_tool(
            ctx,
            AsyncMock(return_value=ToolResult(content=[], is_error=True)),
        )
        _, put_kwargs = mock_store.put.call_args
        saved = put_kwargs["value"]
        self.assertEqual(put_kwargs["ttl"], 3600.0)
        self.assertIsNone(saved["customer_id"])
        self.assertEqual(saved["checksum"], "INVALID")
        self.assertEqual(saved["arguments"]["checksum"], REDACTED_MASK)
        self.assertEqual(saved["status"], AuditStatus.ERROR)

    @patch("ads_mcp.audit.get_access_token", return_value=None)
    async def test_storage_failure_logs_to_dedicated_logger_and_succeeds(
        self, _mock_token
    ):
        """Persistent storage failures log to ads_mcp.audit_storage without breaking tool calls."""
        broken_store = MagicMock()
        broken_store.put = AsyncMock(side_effect=OSError("disk full"))
        middleware = AuditMiddleware(storage=broken_store)
        context = self._make_context(
            name="customers_list_accessible_customers", arguments={}
        )
        expected_result = ToolResult(
            content=[mcp_types.TextContent(type="text", text="1234567890")]
        )
        with self.assertLogs("ads_mcp.audit_storage", level="ERROR") as cm:
            result = await middleware.on_call_tool(
                context, AsyncMock(return_value=expected_result)
            )
        self.assertIs(result, expected_result)
        self.assertIn("disk full", cm.output[0])


class AuditClientIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests driving AuditMiddleware through real FastMCP Client and TasksExtension."""

    @patch("ads_mcp.audit.get_access_token", return_value=None)
    async def test_client_handshake_coercion_errors_and_empty_lists(
        self, _mock_token
    ):
        """Verifies real MCP v2 client_info, validate_only coercion, empty lists, and error classification."""
        server = FastMCP("audit-e2e")
        emitted: list[dict[str, Any]] = []

        class CapturingAuditMiddleware(AuditMiddleware):
            async def emit(self, record: dict[str, Any]) -> None:
                emitted.append(record)

        mw = CapturingAuditMiddleware(server=server)
        server.add_middleware(mw)

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True))
        def read_empty() -> list[str]:
            return []

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=False))
        def mutate_item(
            customer_id: str,
            validate_only: bool = True,
            checksum: str | None = None,
        ) -> str:
            return "committed" if not validate_only else "proposed"

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True))
        def raise_tool_err() -> str:
            raise ToolError("checksum mismatch")

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True))
        def raise_ads_err() -> str:
            ads_ex = GoogleAdsException(
                MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )
            raise ToolError("Google Ads error") from ads_ex

        @server.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True))
        def raise_crash() -> str:
            raise ZeroDivisionError("unexpected bug")

        client_info = mcp_types.Implementation(
            name="antigravity-client", version="2.8.1"
        )
        async with Client(server, client_info=client_info) as client:
            # 1. Empty list return -> status="empty" + real client_info captured
            await client.call_tool("read_empty", {})
            self.assertEqual(emitted[-1]["status"], AuditStatus.EMPTY)
            self.assertEqual(emitted[-1]["mutation_phase"], MutationPhase.READ)
            self.assertEqual(
                emitted[-1]["actor"]["client_info"],
                {"name": "antigravity-client", "version": "2.8.1"},
            )

            # 2. String "false" and integer 0 coerced to False -> logged as COMMIT (not PROPOSE!)
            r_str = await client.call_tool(
                "mutate_item",
                {"customer_id": "123", "validate_only": "false"},
            )
            self.assertEqual(r_str.data, "committed")
            self.assertEqual(
                emitted[-1]["mutation_phase"], MutationPhase.COMMIT
            )

            r_zero = await client.call_tool(
                "mutate_item",
                {"customer_id": "123", "validate_only": 0},
            )
            self.assertEqual(r_zero.data, "committed")
            self.assertEqual(
                emitted[-1]["mutation_phase"], MutationPhase.COMMIT
            )

            # 3. Default omitted validate_only on mutate tool -> PROPOSE
            await client.call_tool("mutate_item", {"customer_id": "123"})
            self.assertEqual(
                emitted[-1]["mutation_phase"], MutationPhase.PROPOSE
            )

            # 4. Smuggling validate_only=False onto a read-only tool stays READ + ValidationError
            await client.call_tool(
                "read_empty", {"validate_only": False}, raise_on_error=False
            )
            self.assertEqual(emitted[-1]["mutation_phase"], MutationPhase.READ)
            self.assertEqual(emitted[-1]["status"], AuditStatus.ERROR)
            self.assertEqual(emitted[-1]["error"], "ValidationError")

            # 5. ToolError vs GoogleAdsException vs NotFoundError vs unhandled crash
            await client.call_tool("raise_tool_err", {}, raise_on_error=False)
            self.assertEqual(emitted[-1]["status"], AuditStatus.ERROR)
            self.assertEqual(emitted[-1]["error"], "ToolError")

            await client.call_tool("raise_ads_err", {}, raise_on_error=False)
            self.assertEqual(emitted[-1]["status"], AuditStatus.ERROR)
            self.assertEqual(emitted[-1]["error"], "GoogleAdsException")

            await client.call_tool("unknown_tool", {}, raise_on_error=False)
            self.assertEqual(emitted[-1]["status"], AuditStatus.ERROR)
            self.assertEqual(emitted[-1]["error"], "NotFoundError")

            await client.call_tool("raise_crash", {}, raise_on_error=False)
            self.assertEqual(emitted[-1]["status"], AuditStatus.FAILED)
            self.assertEqual(emitted[-1]["error"], "ZeroDivisionError")

    @patch("ads_mcp.audit.get_access_token", return_value=None)
    async def test_background_task_enqueued_and_worker_execution_audited(
        self, _mock_token
    ):
        """Background tasks emit both an 'enqueued' tool_call and a 'task_execution' audit record."""
        server = FastMCP("audit-tasks")
        server.add_extension(TasksExtension())
        emitted: list[dict[str, Any]] = []

        class CapturingAuditMiddleware(AuditMiddleware):
            async def emit(self, record: dict[str, Any]) -> None:
                emitted.append(record)

        mw = CapturingAuditMiddleware(server=server)
        server.add_middleware(mw)

        @server.tool(
            task=True,
            annotations=mcp_types.ToolAnnotations(readOnlyHint=False),
        )
        async def async_mutate(
            customer_id: str,
            title: str,
            validate_only: bool = True,
            checksum: str | None = None,
        ) -> str:
            cleaned = customer_id.replace("-", "")
            payload = {"tool": "async_mutate", "title": title}
            items = pac.build_change_items(
                "CREATE", "Video", title, {"Title": title}
            )
            return pac.propose_and_confirm(
                customer_id=cleaned,
                validate_only=validate_only,
                checksum=checksum,
                operation_payload=payload,
                change_items=items,
                validate_fn=None,
                commit_fn=lambda: f"Uploaded {title}",
            )

        mw.instrument_server(server)

        tasks_ext = TasksClientExtension()
        async with Client(server, extensions=[tasks_ext]) as client:
            # 1. Background PROPOSE: records enqueued + worker completion with issued checksum
            t_prop = await call_tool_task(
                client,
                "async_mutate",
                {"customer_id": "123-456-7890", "title": "Launch Ad"},
            )
            prop_res = await t_prop.result()
            self.assertFalse(prop_res.is_error)

            # 2. Background COMMIT with bad checksum: worker ToolError rejection is audited!
            t_bad = await call_tool_task(
                client,
                "async_mutate",
                {
                    "customer_id": "123-456-7890",
                    "title": "Launch Ad",
                    "validate_only": "false",
                    "checksum": "00" * 32,
                },
            )
            with self.assertRaises(ToolError):
                await t_bad.result()

        self.assertEqual(len(emitted), 4)
        enq_prop, run_prop, enq_bad, run_bad = emitted

        self.assertEqual(enq_prop["event"], "tool_call")
        self.assertEqual(enq_prop["status"], AuditStatus.ENQUEUED)
        self.assertEqual(enq_prop["mutation_phase"], MutationPhase.PROPOSE)
        self.assertTrue(enq_prop["task_id"])

        self.assertEqual(run_prop["event"], "task_execution")
        self.assertEqual(run_prop["task_id"], enq_prop["task_id"])
        self.assertEqual(run_prop["call_id"], enq_prop["call_id"])
        self.assertEqual(run_prop["status"], AuditStatus.COMPLETED)
        self.assertEqual(len(run_prop["checksum"]), 64)

        self.assertEqual(enq_bad["event"], "tool_call")
        self.assertEqual(enq_bad["status"], AuditStatus.ENQUEUED)
        self.assertEqual(enq_bad["mutation_phase"], MutationPhase.COMMIT)

        self.assertEqual(run_bad["event"], "task_execution")
        self.assertEqual(run_bad["task_id"], enq_bad["task_id"])
        self.assertEqual(run_bad["mutation_phase"], MutationPhase.COMMIT)
        self.assertEqual(run_bad["status"], AuditStatus.ERROR)
        self.assertEqual(run_bad["error"], "ToolError")

    @patch.dict(
        os.environ,
        {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "888-777-6666"},
        clear=False,
    )
    @patch("ads_mcp.utils.get_googleads_client")
    @patch("ads_mcp.utils.get_googleads_service")
    async def test_coordinator_propose_confirm_checksum_link_and_login_cid_scope(
        self, mock_get_service, mock_get_client
    ):
        """Real coordinator.mcp calls link PROPOSE->COMMIT checksums and omit login_customer_id on CustomerService."""
        import json
        from ads_mcp.coordinator import mcp

        real_ga = GoogleAdsClient(
            credentials=AnonymousCredentials(),
            developer_token="fake-token",
            use_proto_plus=True,
        )
        mock_client = MagicMock()
        mock_label_svc = MagicMock()
        mock_label_resp = MagicMock()
        mock_label_resp.results = [
            SimpleNamespace(resource_name="customers/1234567890/labels/99")
        ]
        mock_label_svc.mutate_labels.return_value = mock_label_resp
        mock_client.get_service.return_value = mock_label_svc
        mock_client.get_type.side_effect = real_ga.get_type
        mock_get_client.return_value = mock_client

        mock_cust_svc = MagicMock()
        mock_cust_svc.list_accessible_customers.return_value = SimpleNamespace(
            resource_names=["customers/1234567890"]
        )
        mock_get_service.return_value = mock_cust_svc

        with self.assertLogs("ads_mcp.audit", level="INFO") as cm:
            async with Client(mcp) as client:
                await client.call_tool(
                    "customers_list_accessible_customers", {}
                )
                prop = await client.call_tool(
                    "labels_manage_labels",
                    {
                        "customer_id": "123-456-7890",
                        "operation": "CREATE",
                        "name": "Q4 Promo",
                    },
                )
                issued_checksum = json.loads(prop.data)["checksum"]
                await client.call_tool(
                    "labels_manage_labels",
                    {
                        "customer_id": "123-456-7890",
                        "operation": "CREATE",
                        "name": "Q4 Promo",
                        "validate_only": False,
                        "checksum": issued_checksum,
                    },
                )

        records = [
            json.loads(line.split("INFO:ads_mcp.audit:", 1)[1])
            for line in cm.output
        ]
        cust_rec, prop_rec, commit_rec = records

        # list_accessible_customers does not accept login_customer_id -> None
        self.assertIsNone(cust_rec["login_customer_id"])
        self.assertEqual(cust_rec["mutation_phase"], MutationPhase.READ)

        # labels_manage_labels inherits env login_customer_id and links PROPOSE -> COMMIT checksum
        self.assertEqual(prop_rec["login_customer_id"], "8887776666")
        self.assertEqual(prop_rec["mutation_phase"], MutationPhase.PROPOSE)
        self.assertEqual(prop_rec["checksum"], issued_checksum)
        self.assertEqual(commit_rec["mutation_phase"], MutationPhase.COMMIT)
        self.assertEqual(commit_rec["checksum"], issued_checksum)
        self.assertEqual(commit_rec["status"], AuditStatus.COMPLETED)


class AuditStorageConfigTest(unittest.IsolatedAsyncioTestCase):
    """Tests for create_audit_storage() and get_audit_storage_ttl() configuration."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(
            lambda: shutil.rmtree(self.temp_dir, ignore_errors=True)
        )
        self.env_keys = [
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_TYPE",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_PATH",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_REDIS_URL",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_FIRESTORE_PROJECT",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_FIRESTORE_DATABASE",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_ENCRYPTION_KEY",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_DISABLE_ENCRYPTION",
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS",
            "GOOGLE_ADS_MCP_STORAGE_TYPE",
            "GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY",
            "GOOGLE_ADS_MCP_JWT_SIGNING_KEY",
            "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET",
        ]
        self.orig_env = {}
        for key in self.env_keys:
            if key in os.environ:
                self.orig_env[key] = os.environ.pop(key)

    def tearDown(self):
        for key in self.env_keys:
            os.environ.pop(key, None)
        for key, val in self.orig_env.items():
            os.environ[key] = val

    def test_create_audit_storage_default_returns_none(self):
        """Audit storage is disabled (None) by default when env vars are unset."""
        self.assertIsNone(create_audit_storage())
        self.assertIsNone(get_audit_storage_ttl())

    def test_audit_storage_stays_unencrypted_without_explicit_audit_key(self):
        """OAuth secrets do not implicitly encrypt audit records so Firestore stays queryable."""
        os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_TYPE"] = "memory"
        os.environ["GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"] = "oauth-secret"
        os.environ["GOOGLE_ADS_MCP_JWT_SIGNING_KEY"] = "jwt-signing-secret"
        store = create_audit_storage()
        self.assertIsInstance(store, MemoryStore)

    async def test_create_audit_storage_encrypted_uses_isolated_hkdf_salt(self):
        """Audit encryption uses a dedicated HKDF salt that cannot decrypt OAuth client storage."""
        path = os.path.join(self.temp_dir, "audit_filetree")
        shared_passphrase = "shared-passphrase-material"
        os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_TYPE"] = "filetree"
        os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_PATH"] = path
        os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_ENCRYPTION_KEY"] = (
            shared_passphrase
        )
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "memory"
        os.environ["GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY"] = shared_passphrase

        audit_store = create_audit_storage()
        client_store = create_client_storage()
        self.assertIsInstance(audit_store, FernetEncryptionWrapper)
        self.assertIsInstance(audit_store.key_value, FileTreeStore)
        self.assertIsInstance(client_store, FernetEncryptionWrapper)

        # Cross-decrypting ciphertext encrypted with client_store's Fernet must fail
        # due to domain-separated HKDF salts.
        await client_store.put("k", {"secret": "tok"}, collection="c")
        raw_entry = await client_store.key_value.get("k", collection="c")
        await audit_store.key_value.put("k", raw_entry, collection="c")
        self.assertIsNone(await audit_store.get("k", collection="c"))

    def test_audit_storage_ttl_parsing_and_validation(self):
        """TTL env var parses positive numbers and rejects zero/negative/invalid values."""
        os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS"] = "86400"
        self.assertEqual(get_audit_storage_ttl(), 86400.0)

        for bad in ("0", "-10", "not-a-number"):
            os.environ["GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS"] = bad
            with self.assertRaises(ValueError):
                get_audit_storage_ttl()

    def test_coordinator_registers_audit_middleware(self):
        """Verify that coordinator.mcp has AuditMiddleware registered."""
        from ads_mcp.coordinator import mcp

        self.assertTrue(
            any(isinstance(mw, AuditMiddleware) for mw in mcp.middleware)
        )


if __name__ == "__main__":
    unittest.main()
