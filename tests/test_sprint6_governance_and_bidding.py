"""Unit tests for Sprint 6 tools: governance, term inspection, bidding readiness, and lead discrepancy."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import unittest

from ads_mcp.tools import intelligence


class TestSprint6Tools(unittest.TestCase):
    @patch("ads_mcp.tools.intelligence.changes.query")
    @patch("ads_mcp.tools.intelligence.changes.customer")
    def test_audit_shared_negative_governance(self, mock_customer, mock_query):
        mock_customer.side_effect = lambda cid: cid

        # 1st call: shared sets
        # 2nd call: active campaigns
        # 3rd call: campaign_shared_set attachments
        mock_query.side_effect = [
            [
                {
                    "shared_set.id": "1001",
                    "shared_set.name": "Orphan List",
                    "shared_set.type": "NEGATIVE_KEYWORDS",
                    "shared_set.member_count": 500,
                    "shared_set.reference_count": 0,
                },
                {
                    "shared_set.id": "1002",
                    "shared_set.name": "Active List",
                    "shared_set.type": "NEGATIVE_KEYWORDS",
                    "shared_set.member_count": 100,
                    "shared_set.reference_count": 2,
                },
            ],
            [
                {
                    "campaign.id": "9991",
                    "campaign.name": "Camp A",
                    "campaign.status": "ENABLED",
                },
                {
                    "campaign.id": "9992",
                    "campaign.name": "Camp B",
                    "campaign.status": "ENABLED",
                },
            ],
            [
                {
                    "campaign_shared_set.campaign": "customers/123/campaigns/9991",
                    "campaign_shared_set.shared_set": "customers/123/sharedSets/1002",
                    "campaign_shared_set.status": "ENABLED",
                }
            ],
        ]

        res = intelligence.audit_shared_negative_governance("123")
        self.assertEqual(res["total_negative_lists_found"], 2)
        self.assertEqual(res["orphaned_negative_lists_count"], 1)
        self.assertEqual(res["total_dormant_negative_terms"], 500)
        self.assertEqual(res["unprotected_campaigns_count"], 1)
        self.assertEqual(res["unprotected_campaigns"][0]["campaign_id"], "9992")

    @patch("ads_mcp.tools.intelligence.changes.query")
    @patch("ads_mcp.tools.intelligence.changes.customer")
    def test_inspect_negative_list_terms(self, mock_customer, mock_query):
        mock_customer.side_effect = lambda cid: cid
        mock_query.return_value = [
            {
                "shared_criterion.shared_set": "customers/123/sharedSets/1001",
                "shared_criterion.criterion_id": "501",
                "shared_criterion.keyword.text": "gratis total",
                "shared_criterion.keyword.match_type": "BROAD",
            },
            {
                "shared_criterion.shared_set": "customers/123/sharedSets/1001",
                "shared_criterion.criterion_id": "502",
                "shared_criterion.keyword.text": "empleo jobs",
                "shared_criterion.keyword.match_type": "PHRASE",
            },
        ]

        res = intelligence.inspect_negative_list_terms(
            "123", "1001", search_query="gratis"
        )
        self.assertEqual(res["total_terms_in_list"], 2)
        self.assertEqual(res["matching_terms_count"], 1)
        self.assertEqual(res["terms_sample"][0]["criterion_id"], "501")

    @patch("ads_mcp.tools.intelligence.changes.query")
    @patch("ads_mcp.tools.intelligence.changes.customer")
    def test_audit_bidding_strategy_readiness(self, mock_customer, mock_query):
        mock_customer.side_effect = lambda cid: cid
        mock_query.return_value = [
            {
                "campaign.id": "1",
                "campaign.name": "Premature Smart Bidding",
                "campaign.bidding_strategy_type": "MAXIMIZE_CONVERSIONS",
                "metrics.conversions": 3.0,
                "metrics.cost_micros": 300_000_000,
                "metrics.cost_per_conversion": 100_000_000,
            },
            {
                "campaign.id": "2",
                "campaign.name": "Ready For Scaling",
                "campaign.bidding_strategy_type": "TARGET_SPEND",
                "metrics.conversions": 45.0,
                "metrics.cost_micros": 450_000_000,
                "metrics.cost_per_conversion": 10_000_000,
            },
        ]

        res = intelligence.audit_bidding_strategy_readiness("123", days=30)
        self.assertEqual(res["premature_smart_bidding_alerts"], 1)
        self.assertEqual(res["ready_for_target_cpa_campaigns"], 1)

    @patch("ads_mcp.tools.intelligence.changes.query")
    @patch("ads_mcp.tools.intelligence.changes.customer")
    def test_audit_lead_to_sale_discrepancy(self, mock_customer, mock_query):
        mock_customer.side_effect = lambda cid: cid
        mock_query.return_value = [
            {
                "metrics.conversions": 20.0,
                "metrics.cost_micros": 1_000_000_000,  # 1000 spend
            }
        ]

        # 2 real calls out of 20 = 10% qualification rate -> ALGORITHMIC_POISONING
        res = intelligence.audit_lead_to_sale_discrepancy(
            "123", real_qualified_calls=2, real_closed_sales=1
        )
        self.assertEqual(res["google_reported_conversions"], 20.0)
        self.assertEqual(res["real_crm_qualified_calls"], 2)
        self.assertEqual(res["lead_qualification_rate_pct"], 10.0)
        self.assertEqual(res["discrepancy_verdict"], "ALGORITHMIC_POISONING")
        self.assertEqual(res["cpa_per_qualified_call"], "500.00")
        self.assertEqual(res["real_cac_per_sale"], "1000.00")


if __name__ == "__main__":
    unittest.main()
