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

"""Test cases for the get_resource_metadata tool."""

import unittest
from unittest.mock import MagicMock, patch

from ads_mcp.tools import get_resource_metadata


class TestGetResourceMetadata(unittest.TestCase):
    """Test cases for the get_resource_metadata tool."""

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_success(
        self, mock_get_type, mock_get_service
    ):
        """Tests that metadata is gathered and categorized correctly using LIKE."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        # Mocking fields
        f1 = MagicMock(selectable=True, filterable=True, sortable=True)
        f1.name = "campaign.id"
        f2 = MagicMock(selectable=True, filterable=False, sortable=True)
        f2.name = "campaign.name"
        f3 = MagicMock(selectable=True, filterable=True, sortable=True)
        f3.name = "ad_group.id"

        mock_service.search_google_ads_fields.return_value = [f1, f2, f3]

        result = get_resource_metadata.get_resource_metadata("campaign")

        # Verify query construction
        expected_query = (
            "SELECT name, selectable, filterable, sortable "
            "WHERE name LIKE 'campaign.%'"
        )
        self.assertEqual(mock_request.query, expected_query)

        # Verify results
        self.assertEqual(result["resource"], "campaign")
        self.assertIn("campaign.id", result["selectable"])
        self.assertIn("campaign.name", result["selectable"])
        self.assertIn("campaign.id", result["filterable"])
        self.assertNotIn("campaign.name", result["filterable"])
        self.assertIn("campaign.id", result["sortable"])
        self.assertIn("campaign.name", result["sortable"])
        self.assertNotIn("ad_group.id", result["selectable"])

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_fallback(
        self, mock_get_type, mock_get_service
    ):
        """Tests fallback query when the first one with LIKE fails."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        # First call fails, second succeeds
        f1 = MagicMock(selectable=True, filterable=True, sortable=True)
        f1.name = "campaign.id"
        mock_service.search_google_ads_fields.side_effect = [
            Exception("API Error"),
            [f1],
        ]

        result = get_resource_metadata.get_resource_metadata("campaign")

        # Verify queries - last set query on mock_request should be the fallback one
        self.assertEqual(
            mock_request.query, "SELECT name, selectable, filterable, sortable"
        )
        self.assertIn("campaign.id", result["selectable"])

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_api_failure(
        self, mock_get_type, mock_get_service
    ):
        """Tests that a RuntimeError is raised if both queries fail."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        # Both calls fail
        mock_service.search_google_ads_fields.side_effect = [
            Exception("Fail 1"),
            Exception("Fail 2"),
        ]

        with self.assertRaises(RuntimeError) as cm:
            get_resource_metadata.get_resource_metadata("campaign")

        self.assertIn(
            "API call to search_google_ads_fields failed: Fail 2",
            str(cm.exception),
        )


if __name__ == "__main__":
    unittest.main()
