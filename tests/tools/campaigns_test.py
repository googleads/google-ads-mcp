import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ads_mcp.tools import campaigns


def mutation_response(name):
    return SimpleNamespace(results=[SimpleNamespace(resource_name=name)])


class TestCampaignDraft(unittest.TestCase):
    @patch("ads_mcp.utils.get_googleads_client")
    def test_creates_only_paused_resources(self, get_client):
        client = MagicMock()
        get_client.return_value = client
        services = {
            "CampaignBudgetService": MagicMock(), "CampaignService": MagicMock(),
            "AdGroupService": MagicMock(), "AdGroupAdService": MagicMock(),
            "AdGroupCriterionService": MagicMock(), "CampaignCriterionService": MagicMock(),
        }
        client.get_service.side_effect = lambda name: services[name]
        services["CampaignBudgetService"].mutate_campaign_budgets.return_value = mutation_response("customers/1/campaignBudgets/1")
        services["CampaignService"].mutate_campaigns.return_value = mutation_response("customers/1/campaigns/1")
        services["AdGroupService"].mutate_ad_groups.return_value = mutation_response("customers/1/adGroups/1")
        services["AdGroupAdService"].mutate_ad_group_ads.return_value = mutation_response("customers/1/adGroupAds/1")
        services["AdGroupCriterionService"].mutate_ad_group_criteria.return_value = SimpleNamespace(results=[MagicMock(), MagicMock()])

        result = campaigns.create_search_campaign_draft(
            "123-456-7890", "Draft", "https://example.com", ["one", "two", "three"],
            ["one", "two"], ["battery recycling", "battery collection"], 1_000_000, ["2826"],
        )

        self.assertEqual(result["status"], "PAUSED_DRAFT")
        campaign = client.get_type("CampaignOperation").create
        self.assertEqual(campaign.status, "PAUSED")
        group = client.get_type("AdGroupOperation").create
        self.assertEqual(group.status, "PAUSED")
        ad = client.get_type("AdGroupAdOperation").create
        self.assertEqual(ad.status, "PAUSED")

    def test_rejects_invalid_rsa_before_api_calls(self):
        with self.assertRaisesRegex(ValueError, "3 to 15 headlines"):
            campaigns.create_search_campaign_draft(
                "123", "Draft", "https://example.com", ["one"], ["one", "two"], ["keyword"], 1
            )
