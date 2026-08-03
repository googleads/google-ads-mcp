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

"""Test cases for the keyword_planner tools."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import keyword_planner


class TestNormalizationHelpers(unittest.TestCase):
    """Tests for the geo/language resource-name normalization helpers."""

    def test_geo_bare_id_is_wrapped(self):
        self.assertEqual(
            keyword_planner._to_geo_resource("2276"),
            "geoTargetConstants/2276",
        )

    def test_geo_resource_name_is_passed_through(self):
        self.assertEqual(
            keyword_planner._to_geo_resource("geoTargetConstants/2276"),
            "geoTargetConstants/2276",
        )

    def test_language_bare_id_is_wrapped(self):
        self.assertEqual(
            keyword_planner._to_language_resource("1001"),
            "languageConstants/1001",
        )

    def test_language_resource_name_is_passed_through(self):
        self.assertEqual(
            keyword_planner._to_language_resource("languageConstants/1001"),
            "languageConstants/1001",
        )


class TestGenerateKeywordIdeas(unittest.TestCase):
    """Test cases for generate_keyword_ideas."""

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_keyword_seed_and_result_formatting(
        self, mock_format, mock_get_service, mock_get_type
    ):
        request = MagicMock()
        mock_get_type.return_value = request
        service = MagicMock()
        mock_get_service.return_value = service
        service.generate_keyword_ideas.return_value = [
            MagicMock(),
            MagicMock(),
        ]
        mock_format.side_effect = [{"text": "a"}, {"text": "b"}]

        results = keyword_planner.generate_keyword_ideas(
            customer_id="1234567890",
            geo_target_constants=["2276"],
            language="1001",
            keywords=["running shoes"],
        )

        mock_get_service.assert_called_once_with("KeywordPlanIdeaService")
        self.assertEqual(request.customer_id, "1234567890")
        self.assertEqual(request.language, "languageConstants/1001")
        request.keyword_seed.keywords.extend.assert_called_once_with(
            ["running shoes"]
        )
        self.assertEqual(results, [{"text": "a"}, {"text": "b"}])

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_keyword_and_url_seed(
        self, mock_format, mock_get_service, mock_get_type
    ):
        request = MagicMock()
        mock_get_type.return_value = request
        mock_get_service.return_value.generate_keyword_ideas.return_value = []

        keyword_planner.generate_keyword_ideas(
            customer_id="1234567890",
            geo_target_constants=["2276"],
            language="1001",
            keywords=["shoes"],
            page_url="https://example.com",
        )

        self.assertEqual(
            request.keyword_and_url_seed.url, "https://example.com"
        )
        request.keyword_and_url_seed.keywords.extend.assert_called_once_with(
            ["shoes"]
        )

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_limit_caps_results(
        self, mock_format, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        mock_get_service.return_value.generate_keyword_ideas.return_value = [
            MagicMock() for _ in range(5)
        ]
        mock_format.side_effect = lambda r: {"idea": id(r)}

        results = keyword_planner.generate_keyword_ideas(
            customer_id="1234567890",
            geo_target_constants=["2276"],
            language="1001",
            keywords=["shoes"],
            limit=2,
        )

        self.assertEqual(len(results), 2)

    def test_missing_seed_raises_tool_error(self):
        with self.assertRaises(ToolError):
            keyword_planner.generate_keyword_ideas(
                customer_id="1234567890",
                geo_target_constants=["2276"],
                language="1001",
            )


class TestGenerateKeywordHistoricalMetrics(unittest.TestCase):
    """Test cases for generate_keyword_historical_metrics."""

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_builds_request_and_formats_results(
        self, mock_format, mock_get_service, mock_get_type
    ):
        request = MagicMock()
        mock_get_type.return_value = request
        service = MagicMock()
        mock_get_service.return_value = service
        response = MagicMock()
        response.results = [MagicMock()]
        service.generate_keyword_historical_metrics.return_value = response
        mock_format.return_value = {"text": "shoes"}

        results = keyword_planner.generate_keyword_historical_metrics(
            customer_id="1234567890",
            keywords=["shoes"],
            geo_target_constants=["2276"],
            language="1001",
        )

        mock_get_service.assert_called_once_with("KeywordPlanIdeaService")
        request.keywords.extend.assert_called_once_with(["shoes"])
        self.assertEqual(results, [{"text": "shoes"}])


class TestReachPlanTools(unittest.TestCase):
    """Test cases for the ReachPlanService tools."""

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_list_plannable_locations(
        self, mock_format, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        service = MagicMock()
        mock_get_service.return_value = service
        response = MagicMock()
        response.plannable_locations = [MagicMock()]
        service.list_plannable_locations.return_value = response
        mock_format.return_value = {"id": "2276"}

        results = keyword_planner.list_plannable_locations()

        mock_get_service.assert_called_once_with("ReachPlanService")
        self.assertEqual(results, [{"id": "2276"}])

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_list_plannable_products(
        self, mock_format, mock_get_service, mock_get_type
    ):
        request = MagicMock()
        mock_get_type.return_value = request
        service = MagicMock()
        mock_get_service.return_value = service
        response = MagicMock()
        response.product_metadata = [MagicMock()]
        service.list_plannable_products.return_value = response
        mock_format.return_value = {"plannable_product_code": "YOUTUBE"}

        results = keyword_planner.list_plannable_products(
            plannable_location_id="2276"
        )

        self.assertEqual(request.plannable_location_id, "2276")
        self.assertEqual(results, [{"plannable_product_code": "YOUTUBE"}])


class TestAudienceInsightsTools(unittest.TestCase):
    """Test cases for the AudienceInsightsService tools."""

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_list_audience_insights_attributes(
        self, mock_format, mock_get_service, mock_get_type
    ):
        request = MagicMock()
        mock_get_type.return_value = request
        service = MagicMock()
        mock_get_service.return_value = service
        response = MagicMock()
        response.attributes = [MagicMock()]
        service.list_audience_insights_attributes.return_value = response
        mock_format.return_value = {"display_name": "Running"}

        results = keyword_planner.list_audience_insights_attributes(
            customer_id="1234567890",
            dimensions=["AFFINITY_USER_INTEREST"],
            query_text="running",
        )

        mock_get_service.assert_called_once_with("AudienceInsightsService")
        self.assertEqual(request.customer_id, "1234567890")
        # customer_insights_group is a required API field; must be set.
        self.assertEqual(request.customer_insights_group, "google-ads-mcp")
        self.assertEqual(request.dimensions, ["AFFINITY_USER_INTEREST"])
        self.assertEqual(request.query_text, "running")
        self.assertEqual(results, [{"display_name": "Running"}])

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_list_insights_eligible_dates(
        self, mock_format, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        service = MagicMock()
        mock_get_service.return_value = service
        response = MagicMock()
        service.list_insights_eligible_dates.return_value = response
        mock_format.return_value = {"data_months": ["2026-06"]}

        result = keyword_planner.list_insights_eligible_dates()

        mock_get_service.assert_called_once_with("AudienceInsightsService")
        self.assertEqual(result, {"data_months": ["2026-06"]})


class TestErrorTranslation(unittest.TestCase):
    """Verifies GoogleAdsException is translated into a ToolError."""

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    def test_google_ads_exception_becomes_tool_error(
        self, mock_get_service, mock_get_type
    ):
        from google.ads.googleads.errors import GoogleAdsException

        mock_get_type.return_value = MagicMock()
        service = MagicMock()
        mock_get_service.return_value = service

        mock_error = MagicMock()
        mock_error.message = "Invalid geo target"
        failure = MagicMock()
        failure.errors = [mock_error]

        ex = GoogleAdsException(
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        ex.failure = failure
        ex.request_id = "req-999"
        service.list_plannable_locations.side_effect = ex

        with self.assertRaises(ToolError) as context:
            keyword_planner.list_plannable_locations()

        self.assertIn("Invalid geo target", str(context.exception))
        self.assertIn("Request ID: req-999", str(context.exception))
