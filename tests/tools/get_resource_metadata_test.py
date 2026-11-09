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
        """Tests that metadata is gathered and merged correctly using two queries."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        # Mocking fields for attributes
        f1 = MagicMock(selectable=True, filterable=True, sortable=True)
        f1.name = "campaign.id"
        f2 = MagicMock(selectable=True, filterable=False, sortable=True)
        f2.name = "campaign.name"

        # Mocking fields for metrics/segments
        f3 = MagicMock(selectable=True, filterable=True, sortable=False)
        f3.name = "metrics.clicks"
        f4 = MagicMock(selectable=True, filterable=True, sortable=False)
        f4.name = "segments.date"

        mock_service.search_google_ads_fields.side_effect = [
            [f1, f2],  # Response for Query 1
            [f3, f4],  # Response for Query 2
        ]

        result = get_resource_metadata.get_resource_metadata("campaign")

        # Verify results
        self.assertEqual(result["resource"], "campaign")
        self.assertIn("campaign.id", result["selectable"])
        self.assertIn("campaign.name", result["selectable"])
        self.assertIn("metrics.clicks", result["selectable"])
        self.assertIn("segments.date", result["selectable"])

        self.assertIn("campaign.id", result["filterable"])
        self.assertNotIn("campaign.name", result["filterable"])
        self.assertIn("metrics.clicks", result["filterable"])
        self.assertIn("segments.date", result["filterable"])

        self.assertIn("campaign.id", result["sortable"])
        self.assertIn("campaign.name", result["sortable"])
        self.assertNotIn("metrics.clicks", result["sortable"])

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_attributes_fallback(
        self, mock_get_type, mock_get_service
    ):
        """Tests fallback for attributes query when the first one fails."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        f1 = MagicMock(selectable=True, filterable=True, sortable=True)
        f1.name = "campaign.id"

        f2 = MagicMock(selectable=True, filterable=True, sortable=False)
        f2.name = "metrics.clicks"

        # 1st call fails, 2nd succeeds (fallback), 3rd succeeds (metrics)
        mock_service.search_google_ads_fields.side_effect = [
            Exception("API Error"),
            [f1],
            [f2],
        ]

        result = get_resource_metadata.get_resource_metadata("campaign")

        self.assertIn("campaign.id", result["selectable"])
        self.assertIn("metrics.clicks", result["selectable"])

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_metrics_failure(
        self, mock_get_type, mock_get_service
    ):
        """Tests that a RuntimeError is raised if the metrics/segments query fails."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_request = MagicMock()
        mock_get_type.return_value = mock_request

        f1 = MagicMock(selectable=True, filterable=True, sortable=True)
        f1.name = "campaign.id"

        # 1st succeeds, 2nd fails
        mock_service.search_google_ads_fields.side_effect = [
            [f1],
            Exception("Metrics Fail"),
        ]

        with self.assertRaises(RuntimeError) as cm:
            get_resource_metadata.get_resource_metadata("campaign")

        self.assertIn(
            "API call to search_google_ads_fields failed: Metrics Fail",
            str(cm.exception),
        )

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

    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.get_googleads_type")
    def test_get_resource_metadata_with_login_customer_id(
        self, mock_get_type, mock_get_service
    ):
        """Tests that get_resource_metadata forwards login_customer_id to get_googleads_service."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_get_type.return_value = MagicMock()
        mock_service.search_google_ads_fields.side_effect = [[], []]

        get_resource_metadata.get_resource_metadata(
            "campaign", login_customer_id="999-888-7777"
        )

        mock_get_service.assert_called_once_with(
            "GoogleAdsFieldService", login_customer_id="999-888-7777"
        )


if __name__ == "__main__":
    unittest.main()
