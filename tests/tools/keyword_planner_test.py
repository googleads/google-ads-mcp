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

import datetime
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


class TestYearMonthRangeResolution(unittest.TestCase):
    """Tests for resolving the requested history window."""

    def test_no_window_requested_returns_none(self):
        # None means "leave the request alone" so the API default of 12 applies.
        self.assertIsNone(
            keyword_planner._resolve_year_month_range(None, None, None)
        )

    @patch("ads_mcp.tools.keyword_planner.datetime")
    def test_months_back_ends_at_last_complete_month(self, mock_datetime):
        mock_datetime.date.today.return_value = datetime.date(2026, 8, 5)

        start, end = keyword_planner._resolve_year_month_range(48, None, None)

        # August 2026 is still running, so the window ends in July 2026.
        self.assertEqual(end, (2026, 7))
        self.assertEqual(start, (2022, 8))

    @patch("ads_mcp.tools.keyword_planner.datetime")
    def test_months_back_of_one_is_a_single_month(self, mock_datetime):
        mock_datetime.date.today.return_value = datetime.date(2026, 1, 20)

        start, end = keyword_planner._resolve_year_month_range(1, None, None)

        self.assertEqual(start, (2025, 12))
        self.assertEqual(end, (2025, 12))

    def test_explicit_window_overrides_months_back(self):
        start, end = keyword_planner._resolve_year_month_range(
            48, "2022-09", "2023-09"
        )

        self.assertEqual(start, (2022, 9))
        self.assertEqual(end, (2023, 9))

    def test_start_only_ends_at_last_complete_month(self):
        with patch(
            "ads_mcp.tools.keyword_planner._last_complete_month",
            return_value=(2026, 7),
        ):
            start, end = keyword_planner._resolve_year_month_range(
                48, "2024-01", None
            )

        self.assertEqual(start, (2024, 1))
        self.assertEqual(end, (2026, 7))

    def test_end_only_counts_months_back_from_end(self):
        start, end = keyword_planner._resolve_year_month_range(
            12, None, "2024-06"
        )

        self.assertEqual(start, (2023, 7))
        self.assertEqual(end, (2024, 6))

    def test_months_back_above_limit_raises(self):
        with self.assertRaises(ToolError) as context:
            keyword_planner._resolve_year_month_range(49, None, None)

        self.assertIn("48", str(context.exception))

    def test_months_back_below_one_raises(self):
        with self.assertRaises(ToolError):
            keyword_planner._resolve_year_month_range(0, None, None)

    def test_inverted_window_raises(self):
        with self.assertRaises(ToolError) as context:
            keyword_planner._resolve_year_month_range(
                None, "2025-01", "2024-01"
            )

        self.assertIn("must not be after", str(context.exception))

    def test_malformed_year_month_raises(self):
        for value in ["2022/09", "2022", "sept-2022", "2022-13", "2022-00"]:
            with self.subTest(value=value):
                with self.assertRaises(ToolError):
                    keyword_planner._resolve_year_month_range(None, value, None)

    def test_apply_sets_offset_month_enum_names(self):
        request = MagicMock()

        keyword_planner._apply_year_month_range(
            request, None, "2022-01", "2023-12"
        )

        year_month_range = request.historical_metrics_options.year_month_range
        # MonthOfYear is offset (JANUARY = 2), so names are set, never numbers.
        self.assertEqual(year_month_range.start.year, 2022)
        self.assertEqual(year_month_range.start.month, "JANUARY")
        self.assertEqual(year_month_range.end.year, 2023)
        self.assertEqual(year_month_range.end.month, "DECEMBER")

    def test_apply_leaves_request_untouched_without_window(self):
        class StrictRequest:
            """Fails on any attribute access, unlike a permissive MagicMock."""

            def __getattr__(self, name):
                raise AssertionError(f"unexpected access to '{name}'")

        # Touching historical_metrics_options would mark the field as present
        # and override the API default of 12 months with an empty range.
        keyword_planner._apply_year_month_range(
            StrictRequest(), None, None, None
        )


class TestNormalizeMonthlyVolumes(unittest.TestCase):
    """Tests decoding the offset MonthOfYear enum in monthly search volumes."""

    def test_offset_enum_becomes_name_and_year_month(self):
        # int64 fields are serialized as strings by proto-plus to_dict.
        metrics = {
            "monthly_search_volumes": [
                {"year": "2024", "month": 2, "monthly_searches": "100"},
                {"year": "2024", "month": 13, "monthly_searches": "300"},
            ]
        }

        keyword_planner._normalize_monthly_volumes(metrics)

        volumes = metrics["monthly_search_volumes"]
        self.assertEqual(volumes[0]["month"], "JANUARY")
        self.assertEqual(volumes[0]["year_month"], "2024-01")
        self.assertEqual(volumes[1]["month"], "DECEMBER")
        self.assertEqual(volumes[1]["year_month"], "2024-12")

    def test_entry_without_year_gets_no_year_month(self):
        metrics = {"monthly_search_volumes": [{"month": 5}]}

        keyword_planner._normalize_monthly_volumes(metrics)

        self.assertEqual(metrics["monthly_search_volumes"][0]["month"], "APRIL")
        self.assertNotIn("year_month", metrics["monthly_search_volumes"][0])

    def test_out_of_range_and_missing_month_are_left_alone(self):
        metrics = {
            "monthly_search_volumes": [
                {"month": 0},
                {"month": 99},
                {"month": "JUNE"},
                {"year": "2024"},
            ]
        }

        keyword_planner._normalize_monthly_volumes(metrics)

        self.assertEqual(
            metrics["monthly_search_volumes"],
            [{"month": 0}, {"month": 99}, {"month": "JUNE"}, {"year": "2024"}],
        )

    def test_non_dict_metrics_are_ignored(self):
        # Results without metrics format to a dict lacking the metrics key.
        keyword_planner._normalize_monthly_volumes(None)
        keyword_planner._normalize_monthly_volumes({})


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

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    @patch("ads_mcp.tools.keyword_planner._apply_year_month_range")
    def test_history_window_defaults_to_api_default(
        self, mock_apply, mock_format, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        mock_get_service.return_value.generate_keyword_ideas.return_value = []

        keyword_planner.generate_keyword_ideas(
            customer_id="1234567890",
            geo_target_constants=["2276"],
            language="1001",
            keywords=["shoes"],
        )

        # months_back stays None here: a long window multiplies the response by
        # one monthly volume entry per idea per month.
        self.assertEqual(mock_apply.call_args[0][1:], (None, None, None))

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    def test_history_window_is_forwarded(
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
            start_year_month="2022-09",
            end_year_month="2026-07",
        )

        year_month_range = request.historical_metrics_options.year_month_range
        self.assertEqual(year_month_range.start.year, 2022)
        self.assertEqual(year_month_range.start.month, "SEPTEMBER")
        self.assertEqual(year_month_range.end.year, 2026)
        self.assertEqual(year_month_range.end.month, "JULY")

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    def test_monthly_volumes_are_normalized(
        self, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        mock_get_service.return_value.generate_keyword_ideas.return_value = [
            MagicMock()
        ]

        with patch(
            "ads_mcp.utils.format_output_value",
            return_value={
                "text": "shoes",
                "keyword_idea_metrics": {
                    "monthly_search_volumes": [{"year": "2024", "month": 2}]
                },
            },
        ):
            results = keyword_planner.generate_keyword_ideas(
                customer_id="1234567890",
                geo_target_constants=["2276"],
                language="1001",
                keywords=["shoes"],
            )

        volume = results[0]["keyword_idea_metrics"]["monthly_search_volumes"][0]
        self.assertEqual(volume["year_month"], "2024-01")

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

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    @patch("ads_mcp.utils.format_output_value")
    @patch("ads_mcp.tools.keyword_planner._last_complete_month")
    def test_defaults_to_full_four_year_window(
        self, mock_last_month, mock_format, mock_get_service, mock_get_type
    ):
        mock_last_month.return_value = (2026, 7)
        request = MagicMock()
        mock_get_type.return_value = request
        mock_get_service.return_value.generate_keyword_historical_metrics.return_value.results = (
            []
        )

        keyword_planner.generate_keyword_historical_metrics(
            customer_id="1234567890",
            keywords=["shoes"],
            geo_target_constants=["2276"],
            language="1001",
        )

        year_month_range = request.historical_metrics_options.year_month_range
        self.assertEqual(year_month_range.start.year, 2022)
        self.assertEqual(year_month_range.start.month, "AUGUST")
        self.assertEqual(year_month_range.end.year, 2026)
        self.assertEqual(year_month_range.end.month, "JULY")

    @patch("ads_mcp.utils.get_googleads_type")
    @patch("ads_mcp.utils.get_googleads_service")
    def test_monthly_volumes_are_normalized(
        self, mock_get_service, mock_get_type
    ):
        mock_get_type.return_value = MagicMock()
        response = MagicMock()
        response.results = [MagicMock()]
        mock_get_service.return_value.generate_keyword_historical_metrics.return_value = (
            response
        )

        with patch(
            "ads_mcp.utils.format_output_value",
            return_value={
                "text": "shoes",
                "keyword_metrics": {
                    "monthly_search_volumes": [
                        {"year": "2022", "month": 9, "monthly_searches": "40"}
                    ]
                },
            },
        ):
            results = keyword_planner.generate_keyword_historical_metrics(
                customer_id="1234567890",
                keywords=["shoes"],
                geo_target_constants=["2276"],
                language="1001",
            )

        volume = results[0]["keyword_metrics"]["monthly_search_volumes"][0]
        self.assertEqual(volume["month"], "AUGUST")
        self.assertEqual(volume["year_month"], "2022-08")


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
