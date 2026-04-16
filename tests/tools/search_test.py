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

"""Test cases for the search tool."""

import unittest
from unittest.mock import MagicMock, patch, mock_open

from ads_mcp.tools import search


class TestSearch(unittest.TestCase):
    """Test cases for the search tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_row")
    def test_search_basic(self, mock_format_row, mock_get_service):
        """Tests that the search function constructs the correct query and processes results."""
        # Setup mock service and search stream
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # Mock result results
        mock_batch = MagicMock()
        mock_batch.results = [MagicMock(), MagicMock()]
        mock_batch.field_mask.paths = ["campaign.id", "campaign.name"]
        mock_service.search_stream.return_value = [mock_batch]

        mock_format_row.side_effect = [
            {"id": 1, "name": "C1"},
            {"id": 2, "name": "C2"},
        ]

        # Call search
        results = search.search(
            customer_id="1234567890",
            fields=["campaign.id", "campaign.name"],
            resource="campaign",
            conditions=["campaign.status = 'ENABLED'"],
            orderings=["campaign.name ASC"],
            limit=10,
        )

        # Verify query
        expected_query = (
            "SELECT campaign.id,campaign.name FROM campaign "
            "WHERE campaign.status = 'ENABLED' "
            "ORDER BY campaign.name ASC "
            "LIMIT 10 "
            "PARAMETERS omit_unselected_resource_names=true"
        )
        mock_service.search_stream.assert_called_once_with(
            customer_id="1234567890", query=expected_query
        )

        # Verify results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[1]["name"], "C2")

    def test_search_tool_description(self):
        """Tests that the tool description is generated correctly."""
        # Mocking open as if the file exists
        m = mock_open(read_data="resource1: field1, field2")
        with patch("builtins.open", m):
            with patch(
                "ads_mcp.utils.get_gaql_resources_filepath",
                return_value="/fake/path",
            ):
                description = search._search_tool_description()
                self.assertIn("resource1: field1, field2", description)
                self.assertIn("Query Grammar", description)

    def test_search_tool_description_file_not_found(self):
        """Tests that the tool description handles missing file correctly."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            with patch(
                "ads_mcp.utils.get_gaql_resources_filepath",
                return_value="/fake/path",
            ):
                with patch("ads_mcp.utils.logger.error") as mock_log_error:
                    description = search._search_tool_description()
                    self.assertIn(
                        "WARNING: The list of valid resources is missing.",
                        description,
                    )
                    mock_log_error.assert_called_once()

    @patch("ads_mcp.utils.get_googleads_service")
    def test_search_google_ads_exception(self, mock_get_service):
        """Tests that search handles GoogleAdsException and returns an error dict."""
        from google.ads.googleads.errors import GoogleAdsException

        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # Mock failure object
        mock_error = MagicMock()
        mock_error.message = "Invalid field name"
        mock_failure = MagicMock()
        mock_failure.errors = [mock_error]

        # Instantiate real exception with dummy args
        mock_ex = GoogleAdsException(
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        mock_ex.failure = mock_failure
        mock_ex.request_id = "req-123"

        mock_service.search_stream.side_effect = mock_ex

        # Call search and verify it raises ToolError
        from fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError) as context:
            search.search(
                customer_id="1234567890",
                fields=["invalid_field"],
                resource="campaign",
            )

        # Verify error message
        self.assertIn(
            "Google Ads API Error: Invalid field name", str(context.exception)
        )
        self.assertIn("Request ID: req-123", str(context.exception))
