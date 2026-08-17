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

"""Test cases for the mutate tool."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import mutate

from google.ads.googleads.v25.services.types.google_ads_service import (
    MutateGoogleAdsRequest,
    MutateGoogleAdsResponse,
    MutateOperation,
)

_CREATE_BUDGET = {
    "campaign_budget_operation": {
        "create": {
            "resource_name": "customers/1234567890/campaignBudgets/-1",
            "name": "Example budget",
            "amount_micros": 20000000,
            "delivery_method": "STANDARD",
        }
    }
}


def _fake_client() -> MagicMock:
    """Returns a client whose get_type yields real proto-plus messages."""
    types = {
        "MutateOperation": MutateOperation,
        "MutateGoogleAdsRequest": MutateGoogleAdsRequest,
    }
    client = MagicMock()
    client.get_type.side_effect = lambda name: types[name]()
    return client


class TestMutate(unittest.TestCase):
    """Test cases for the mutate tool."""

    def setUp(self):
        client_patcher = patch("ads_mcp.utils.get_googleads_client")
        service_patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_client = client_patcher.start()
        self.mock_get_service = service_patcher.start()
        self.addCleanup(client_patcher.stop)
        self.addCleanup(service_patcher.stop)

        self.mock_get_client.return_value = _fake_client()
        self.mock_service = MagicMock()
        self.mock_service.mutate.return_value = MutateGoogleAdsResponse()
        self.mock_get_service.return_value = self.mock_service

    def _sent_request(self) -> MutateGoogleAdsRequest:
        """Returns the request the tool passed to the API."""
        return self.mock_service.mutate.call_args.kwargs["request"]

    def test_defaults_to_dry_run(self):
        """Nothing is applied unless validate_only is explicitly disabled."""
        result = mutate.mutate(
            customer_id="1234567890", operations=[_CREATE_BUDGET]
        )

        request = self._sent_request()
        self.assertTrue(request.validate_only)
        self.assertFalse(result["applied"])
        self.assertIn("NOTHING was changed", result["message"])

    def test_applies_when_validate_only_disabled(self):
        """validate_only=False sends a real mutation."""
        result = mutate.mutate(
            customer_id="1234567890",
            operations=[_CREATE_BUDGET],
            validate_only=False,
        )

        self.assertFalse(self._sent_request().validate_only)
        self.assertTrue(result["applied"])

    def test_builds_operation_and_normalizes_customer_id(self):
        """Hyphenated customer ids are accepted and operations are converted."""
        result = mutate.mutate(
            customer_id="123-456-7890", operations=[_CREATE_BUDGET]
        )

        request = self._sent_request()
        self.assertEqual("1234567890", request.customer_id)
        self.assertEqual("1234567890", result["customer_id"])
        self.assertEqual(1, len(request.mutate_operations))
        self.assertEqual(
            "campaign_budget_operation",
            request.mutate_operations[0]._pb.WhichOneof("operation"),
        )

    def test_update_mask_is_derived_from_set_fields(self):
        """An update without an explicit mask gets one covering its fields."""
        mutate.mutate(
            customer_id="1234567890",
            operations=[
                {
                    "campaign_operation": {
                        "update": {
                            "resource_name": "customers/1234567890/campaigns/9",
                            "status": "PAUSED",
                        }
                    }
                }
            ],
        )

        operation = self._sent_request().mutate_operations[0]
        paths = list(operation.campaign_operation.update_mask.paths)
        self.assertIn("status", paths)

    def test_explicit_update_mask_is_preserved(self):
        """A caller-supplied mask is not overwritten."""
        mutate.mutate(
            customer_id="1234567890",
            operations=[
                {
                    "campaign_operation": {
                        "update": {
                            "resource_name": "customers/1234567890/campaigns/9",
                            "status": "PAUSED",
                            "name": "New name",
                        },
                        "update_mask": {"paths": ["name"]},
                    }
                }
            ],
        )

        operation = self._sent_request().mutate_operations[0]
        self.assertEqual(
            ["name"], list(operation.campaign_operation.update_mask.paths)
        )

    def test_remove_operation_needs_no_mask(self):
        """Remove operations pass through untouched."""
        mutate.mutate(
            customer_id="1234567890",
            operations=[
                {
                    "ad_group_operation": {
                        "remove": "customers/1234567890/adGroups/5"
                    }
                }
            ],
        )

        operation = self._sent_request().mutate_operations[0]
        self.assertEqual(
            "customers/1234567890/adGroups/5",
            operation.ad_group_operation.remove,
        )

    def test_results_report_resource_names(self):
        """Each operation response is summarized."""
        self.mock_service.mutate.return_value = MutateGoogleAdsResponse(
            {
                "mutate_operation_responses": [
                    {
                        "campaign_budget_result": {
                            "resource_name": "customers/1234567890/campaignBudgets/7"
                        }
                    }
                ]
            }
        )

        result = mutate.mutate(
            customer_id="1234567890", operations=[_CREATE_BUDGET]
        )

        self.assertEqual(
            [
                {
                    "operation": "campaign_budget_result",
                    "resource_name": "customers/1234567890/campaignBudgets/7",
                }
            ],
            result["results"],
        )

    def test_empty_operations_rejected(self):
        """An empty batch is a caller error, not an API round trip."""
        with self.assertRaises(ToolError):
            mutate.mutate(customer_id="1234567890", operations=[])
        self.mock_service.mutate.assert_not_called()

    def test_unknown_field_reports_operation_index(self):
        """Invalid operations name the offending index."""
        with self.assertRaises(ToolError) as ctx:
            mutate.mutate(
                customer_id="1234567890",
                operations=[
                    _CREATE_BUDGET,
                    {"campaign_operation": {"create": {"not_a_field": 1}}},
                ],
            )
        self.assertIn("operations[1]", str(ctx.exception))

    def test_operation_without_oneof_rejected(self):
        """An operation that sets no resource operation is rejected."""
        with self.assertRaises(ToolError):
            mutate.mutate(customer_id="1234567890", operations=[{}])

    def test_partial_failure_conflicts_with_validate_only(self):
        """The two flags are mutually exclusive in the API."""
        with self.assertRaises(ToolError):
            mutate.mutate(
                customer_id="1234567890",
                operations=[_CREATE_BUDGET],
                validate_only=True,
                partial_failure=True,
            )
        self.mock_service.mutate.assert_not_called()

    def test_invalid_response_content_type_rejected(self):
        """Only the two documented content types are accepted."""
        with self.assertRaises(ToolError):
            mutate.mutate(
                customer_id="1234567890",
                operations=[_CREATE_BUDGET],
                response_content_type="EVERYTHING",
            )

    def test_google_ads_exception_becomes_tool_error(self):
        """API failures surface as ToolError with the request id."""
        from google.ads.googleads.errors import GoogleAdsException

        failure = MagicMock()
        error = MagicMock()
        error.message = "Budget amount is too low."
        error.location.field_path_elements = []
        failure.errors = [error]

        self.mock_service.mutate.side_effect = GoogleAdsException(
            None, None, failure, "req-123"
        )

        with self.assertRaises(ToolError) as ctx:
            mutate.mutate(customer_id="1234567890", operations=[_CREATE_BUDGET])

        message = str(ctx.exception)
        self.assertIn("req-123", message)
        self.assertIn("Budget amount is too low.", message)


if __name__ == "__main__":
    unittest.main()
