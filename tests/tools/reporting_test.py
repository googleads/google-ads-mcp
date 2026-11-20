"""Tests for the dedicated reporting workflows."""

import unittest
from unittest.mock import patch

from ads_mcp.tools import reporting


class ReportingToolsTest(unittest.TestCase):
    @patch("ads_mcp.tools.reporting.search")
    def test_campaign_diagnostics_scopes_date_and_account(self, search):
        search.return_value = []
        reporting.campaign_diagnostics(
            "123",
            start_date="2026-01-01",
            end_date="2026-01-31",
            account_name="client_a",
        )
        kwargs = search.call_args.kwargs
        self.assertEqual(kwargs["resource"], "campaign")
        self.assertEqual(kwargs["account_name"], "client_a")
        self.assertIn(
            "segments.date BETWEEN '2026-01-01' AND '2026-01-31'",
            kwargs["conditions"],
        )

    @patch("ads_mcp.tools.reporting.search")
    def test_search_terms_uses_search_term_view(self, search):
        search.return_value = []
        reporting.search_term_report("123")
        self.assertEqual(
            search.call_args.kwargs["resource"], "search_term_view"
        )

    def test_dates_must_be_provided_together(self):
        with self.assertRaises(ValueError):
            reporting.budget_report("123", start_date="2026-01-01")

    def test_anomaly_threshold_is_positive(self):
        with self.assertRaises(ValueError):
            reporting.performance_anomalies("123", threshold_percent=0)

    @patch("ads_mcp.tools.reporting.search")
    def test_anomalies_report_material_day_over_day_change(self, search):
        search.return_value = [
            {
                "campaign.id": "1",
                "campaign.name": "Campaign",
                "segments.date": "2026-01-01",
                "metrics.clicks": 10,
                "metrics.cost_micros": 100,
                "metrics.conversions": 1,
            },
            {
                "campaign.id": "1",
                "campaign.name": "Campaign",
                "segments.date": "2026-01-02",
                "metrics.clicks": 20,
                "metrics.cost_micros": 100,
                "metrics.conversions": 1,
            },
        ]
        anomalies = reporting.performance_anomalies("123", threshold_percent=30)
        self.assertEqual(anomalies[0]["metric"], "metrics.clicks")
        self.assertEqual(anomalies[0]["change_percent"], 100.0)
