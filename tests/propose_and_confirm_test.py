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

"""Unit tests for the generalized propose-and-confirm workflow utilities."""

import json
import unittest
from unittest.mock import MagicMock

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.errors.types.errors import (
    ErrorCode,
    GoogleAdsError,
    GoogleAdsFailure,
)
from google.ads.googleads.v25.errors.types.request_error import RequestErrorEnum
from google.ads.googleads.v25.services.types.asset_service import AssetOperation
from ads_mcp import propose_and_confirm as pac
from ads_mcp import utils


class TestProposeAndConfirm(unittest.TestCase):
    """Tests for ads_mcp.propose_and_confirm."""

    def test_build_change_items_skips_none_and_formats_values(self):
        """Tests that build_change_items skips None fields and formats complex values."""
        items = pac.build_change_items(
            operation=utils.MutateOperation.UPDATE.value,
            entity_readable="Label",
            primary_key_readable="customers/123/labels/456",
            fields={
                "Name": "New Name",
                "Background Color": None,
                "Tags": ["a", "b"],
                "Operation Enum": utils.MutateOperation.UPDATE,
            },
            original_fields={"Name": "Old Name"},
        )

        self.assertEqual(len(items), 3)
        self.assertEqual(
            items[0].to_dict(),
            {
                "operation": "UPDATE",
                "entity_readable": "Label",
                "primary_key_readable": "customers/123/labels/456",
                "field_readable": "Name",
                "value_readable": "New Name",
                "original_value_readable": "Old Name",
            },
        )
        self.assertNotIn("original_value_readable", items[1].to_dict())
        self.assertEqual(items[1].value_readable, '["a", "b"]')
        self.assertEqual(items[2].value_readable, "UPDATE")

    def test_compute_checksum_deterministic_across_dict_key_order(self):
        """Tests that compute_checksum is deterministic regardless of dict key order."""
        payload_a = {
            "tool": "create_asset",
            "name": "Headline 1",
            "final_urls": ["https://example.com"],
            "nested": {"b": 2, "a": 1},
            "binary": b"raw_image_bytes",
        }
        payload_b = {
            "binary": b"raw_image_bytes",
            "nested": {"a": 1, "b": 2},
            "final_urls": ["https://example.com"],
            "name": "Headline 1",
            "tool": "create_asset",
        }

        checksum_a = pac.compute_checksum("1234567890", payload_a)
        checksum_b = pac.compute_checksum("1234567890", payload_b)
        self.assertEqual(checksum_a, checksum_b)
        self.assertEqual(len(checksum_a), 64)

        # Uppercase and padded checksum strings verify cleanly
        self.assertIsNone(
            pac.verify_checksum(
                "1234567890", payload_a, f"  {checksum_a.upper()}  "
            )
        )

        # Changing customer_id or payload changes checksum
        self.assertNotEqual(
            checksum_a, pac.compute_checksum("9999999999", payload_a)
        )
        payload_modified = dict(payload_a, binary=b"different_image_bytes")
        self.assertNotEqual(
            checksum_a, pac.compute_checksum("1234567890", payload_modified)
        )

    def test_compute_checksum_with_proto_messages_and_framing(self):
        """Tests that compute_checksum deterministically hashes proto messages and frames list items."""
        op1 = AssetOperation()
        op1.create.name = "Proto Asset"
        op1.create.text_asset.text = "Hello World"

        op2 = AssetOperation()
        op2.create.text_asset.text = "Hello World"
        op2.create.name = "Proto Asset"

        self.assertEqual(
            pac.compute_checksum("1234567890", [op1]),
            pac.compute_checksum("1234567890", [op2]),
        )
        self.assertEqual(
            pac.compute_checksum("1234567890", [type(op1).pb(op1)]),
            pac.compute_checksum("1234567890", [type(op2).pb(op2)]),
        )

        op3 = AssetOperation()
        op3.create.name = "Different Proto Asset"
        op3.create.text_asset.text = "Hello World"
        self.assertNotEqual(
            pac.compute_checksum("1234567890", [op1]),
            pac.compute_checksum("1234567890", [op3]),
        )
        # Multi-operation list must not collide with single operation or reordered list
        self.assertNotEqual(
            pac.compute_checksum("1234567890", [op1]),
            pac.compute_checksum("1234567890", [op1, AssetOperation()]),
        )
        self.assertNotEqual(
            pac.compute_checksum("1234567890", [op1, op3]),
            pac.compute_checksum("1234567890", [op3, op1]),
        )

    def test_propose_and_confirm_round_trip(self):
        """Tests full propose (validate_only=True) and confirm (validate_only=False) workflow."""
        validate_mock = MagicMock()
        commit_mock = MagicMock(return_value="Successfully mutated resource.")
        payload = {"tool": "test_tool", "name": "Test Entity"}
        items = pac.build_change_items(
            operation="CREATE",
            entity_readable="Test Entity",
            primary_key_readable="Test Entity",
            fields={"Name": "Test Entity"},
        )

        # 1. Propose phase (validate_only=True)
        propose_res = pac.propose_and_confirm(
            customer_id="1234567890",
            validate_only=True,
            checksum=None,
            operation_payload=payload,
            change_items=items,
            validate_fn=validate_mock,
            commit_fn=commit_mock,
        )
        validate_mock.assert_called_once()
        commit_mock.assert_not_called()

        proposal = json.loads(propose_res)
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertTrue(proposal["validate_only"])
        self.assertEqual(proposal["customer_id"], "1234567890")
        self.assertEqual(len(proposal["change_items"]), 1)
        checksum = proposal["checksum"]
        self.assertTrue(checksum)

        # 2. Confirm phase (validate_only=False) with valid checksum (case-insensitive)
        confirm_res = pac.propose_and_confirm(
            customer_id="1234567890",
            validate_only=False,
            checksum=checksum.upper(),
            operation_payload=payload,
            change_items=items,
            validate_fn=validate_mock,
            commit_fn=commit_mock,
        )
        self.assertEqual(confirm_res, "Successfully mutated resource.")
        commit_mock.assert_called_once()

    def test_propose_and_confirm_rejects_missing_or_mismatched_checksum(self):
        """Tests that validate_only=False raises ToolError on missing or mismatched checksums."""
        commit_mock = MagicMock(return_value="Should not execute")
        payload = {"tool": "test_tool", "name": "Approved Name"}
        valid_checksum = pac.compute_checksum("1234567890", payload)

        # Missing checksum
        with self.assertRaisesRegex(
            ToolError,
            "checksum from a previous validate_only=True call is required",
        ):
            pac.propose_and_confirm(
                customer_id="1234567890",
                validate_only=False,
                checksum=None,
                operation_payload=payload,
                change_items=[],
                commit_fn=commit_mock,
            )
        commit_mock.assert_not_called()

        # Mismatched payload
        with self.assertRaisesRegex(
            ToolError, "Invalid or mismatched checksum"
        ):
            pac.propose_and_confirm(
                customer_id="1234567890",
                validate_only=False,
                checksum=valid_checksum,
                operation_payload={"tool": "test_tool", "name": "Tampered"},
                change_items=[],
                commit_fn=commit_mock,
            )
        commit_mock.assert_not_called()

        # Mismatched customer_id
        with self.assertRaisesRegex(
            ToolError, "Invalid or mismatched checksum"
        ):
            pac.propose_and_confirm(
                customer_id="9999999999",
                validate_only=False,
                checksum=valid_checksum,
                operation_payload=payload,
                change_items=[],
                commit_fn=commit_mock,
            )
        commit_mock.assert_not_called()

    def test_propose_and_confirm_handles_validation_and_commit_errors(self):
        """Tests that exceptions in validate_fn or commit_fn raise formatted ToolErrors."""
        payload = {"tool": "test_tool", "name": "Test"}
        valid_checksum = pac.compute_checksum("1234567890", payload)

        with self.assertRaisesRegex(
            ToolError, "Failed to mutate: API dry-run error"
        ):
            pac.propose_and_confirm(
                customer_id="1234567890",
                validate_only=True,
                checksum=None,
                operation_payload=payload,
                change_items=[],
                validate_fn=MagicMock(
                    side_effect=RuntimeError("API dry-run error")
                ),
                commit_fn=MagicMock(),
                error_prefix="Failed to mutate",
            )

        with self.assertRaisesRegex(
            ToolError, "Failed to mutate: API commit error"
        ):
            pac.propose_and_confirm(
                customer_id="1234567890",
                validate_only=False,
                checksum=valid_checksum,
                operation_payload=payload,
                change_items=[],
                commit_fn=MagicMock(
                    side_effect=RuntimeError("API commit error")
                ),
                error_prefix="Failed to mutate",
            )

    def test_propose_and_confirm_formats_google_ads_exception(self):
        """Tests that GoogleAdsException details are formatted cleanly into ToolError."""
        failure = GoogleAdsFailure(
            errors=[
                GoogleAdsError(
                    error_code=ErrorCode(
                        request_error=RequestErrorEnum.RequestError.BAD_RESOURCE_ID
                    ),
                    message="Invalid customer ID.",
                )
            ]
        )
        ga_ex = GoogleAdsException(
            error=MagicMock(),
            call=MagicMock(),
            failure=type(failure).pb(failure),
            request_id="req-abc-123",
        )
        with self.assertRaises(ToolError) as ctx:
            pac.propose_and_confirm(
                customer_id="1234567890",
                validate_only=True,
                checksum=None,
                operation_payload={"tool": "test"},
                change_items=[],
                validate_fn=MagicMock(side_effect=ga_ex),
                commit_fn=MagicMock(),
                error_prefix="Failed to create asset",
            )
        msg = str(ctx.exception)
        self.assertIn("Failed to create asset:", msg)
        self.assertIn("Request ID: req-abc-123", msg)
        self.assertIn("Invalid customer ID.", msg)


if __name__ == "__main__":
    unittest.main()
