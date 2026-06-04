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

"""Test cases for the mutate_core module."""

import os
import unittest
from unittest import mock

from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from ads_mcp.tools import mutate_core


def _test_client() -> GoogleAdsClient:
    """Returns a GoogleAdsClient for unit tests without live credentials."""
    with mock.patch("google.auth.default") as auth_default:
        auth_default.return_value = (mock.MagicMock(), None)
        return GoogleAdsClient(
            credentials=mock.MagicMock(),
            developer_token="test-token",
            use_proto_plus=True,
        )


class TestMutateCore(unittest.TestCase):
    """Test cases for the GoogleAdsService.mutate wrapper."""

    def setUp(self):
        """Sets the developer token required to construct the API client."""
        os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"] = "test-token"
        self._client = _test_client()

    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_type")
    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_service")
    def test_execute_mutate_single_chunk(self, mock_get_service, mock_get_type):
        """Tests mutate with one chunk and normalized customer_id."""
        mock_get_type.side_effect = self._client.get_type
        mock_response = mock.MagicMock()
        mock_response.mutate_operation_responses = [mock.MagicMock()]
        mock_response.partial_failure_error = None
        mock_get_service.return_value.mutate.return_value = mock_response

        result = mutate_core.execute_mutate(
            customer_id="123-456-7890",
            operations=[
                {
                    "campaignOperation": {
                        "update": {
                            "resourceName": "customers/1/campaigns/2",
                            "status": "PAUSED",
                        },
                        "updateMask": "status",
                    }
                }
            ],
            validate_only=True,
        )

        mock_get_service.return_value.mutate.assert_called_once()
        call_request = mock_get_service.return_value.mutate.call_args.kwargs[
            "request"
        ]
        self.assertEqual(call_request.customer_id, "1234567890")
        self.assertTrue(call_request.validate_only)
        self.assertEqual(len(call_request.mutate_operations), 1)
        self.assertIn("mutate_operation_responses", result)

    @mock.patch("ads_mcp.tools.mutate_core.feature_flags.mutate_chunk_size")
    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_type")
    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_service")
    def test_execute_mutate_chunks(
        self, mock_get_service, mock_get_type, mock_chunk_size
    ):
        """Tests that large operation lists are split across mutate calls."""
        mock_chunk_size.return_value = 1
        mock_get_type.side_effect = self._client.get_type
        mock_response = mock.MagicMock()
        mock_response.mutate_operation_responses = [mock.MagicMock()]
        mock_response.partial_failure_error = None
        mock_get_service.return_value.mutate.return_value = mock_response

        mutate_core.execute_mutate(
            customer_id="1",
            operations=[
                {
                    "campaignOperation": {
                        "update": {
                            "resourceName": "customers/1/campaigns/1",
                            "status": "PAUSED",
                        },
                        "updateMask": "status",
                    }
                },
                {
                    "campaignOperation": {
                        "update": {
                            "resourceName": "customers/1/campaigns/2",
                            "status": "ENABLED",
                        },
                        "updateMask": "status",
                    }
                },
            ],
        )

        self.assertEqual(mock_get_service.return_value.mutate.call_count, 2)

    def test_execute_mutate_empty_operations(self):
        """Tests that an empty operations list raises ToolError."""
        with self.assertRaises(ToolError):
            mutate_core.execute_mutate(customer_id="1", operations=[])

    def test_parse_invalid_operation_type(self):
        """Tests that non-dict operations raise ToolError during parsing."""
        with self.assertRaises(ToolError):
            mutate_core._parse_operations(["not-a-dict"])

    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_type")
    @mock.patch("ads_mcp.tools.mutate_core.utils.get_googleads_service")
    def test_google_ads_exception(self, mock_get_service, mock_get_type):
        """Tests that GoogleAdsException is converted to ToolError."""
        mock_get_type.side_effect = self._client.get_type
        ex = GoogleAdsException(
            error=mock.MagicMock(),
            call=mock.MagicMock(),
            failure=mock.MagicMock(errors=[mock.MagicMock(message="boom")]),
            request_id="req-1",
        )
        mock_get_service.return_value.mutate.side_effect = ex

        with self.assertRaises(ToolError) as ctx:
            mutate_core.execute_mutate(
                customer_id="1",
                operations=[
                    {
                        "campaignOperation": {
                            "update": {
                                "resourceName": "customers/1/campaigns/2",
                                "status": "PAUSED",
                            },
                            "updateMask": "status",
                        }
                    }
                ],
            )
        self.assertIn("req-1", str(ctx.exception))
