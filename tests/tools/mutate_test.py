# Copyright 2026 Rodrigo Palma.
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

"""Test cases for the mutate tools."""

import importlib.resources
import os
import unittest
from collections import defaultdict
from unittest.mock import MagicMock, patch

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.oauth2.credentials import Credentials

from ads_mcp.config import ToolsConfig
from ads_mcp.coordinator import initialize_and_mount_tools
from ads_mcp.tools import mutate

MUTATE_TOOL_NAMES = [
    "mutate_add_negative_keywords",
    "mutate_set_ad_group_cpc_bid",
    "mutate_set_ad_group_status",
    "mutate_set_ad_status",
    "mutate_set_campaign_status",
    "mutate_set_keyword_cpc_bid",
    "mutate_update_campaign_budget",
]


class MutateToolTestCase(unittest.TestCase):
    """Runs the tools against a real client whose services are mocked."""

    def setUp(self):
        self.client = GoogleAdsClient(
            credentials=Credentials(token="fake"), use_proto_plus=True
        )
        self.services = defaultdict(MagicMock)
        self.client.get_service = MagicMock(
            side_effect=lambda name, **kwargs: self.services[name]
        )
        patcher = patch(
            "ads_mcp.utils.get_googleads_client", return_value=self.client
        )
        self.get_client = patcher.start()
        self.addCleanup(patcher.stop)

    def set_rows(self, *rows):
        self.services["GoogleAdsService"].search.return_value = list(rows)

    def make_row(self, fields):
        row = self.client.get_type("GoogleAdsRow")
        for path, value in fields.items():
            *parents, leaf = path.split(".")
            message = row
            for parent in parents:
                message = getattr(message, parent)
            setattr(message, leaf, value)
        return row

    def sent_request(self, service_name, method_name):
        method = getattr(self.services[service_name], method_name)
        method.assert_called_once()
        return method.call_args.kwargs["request"]

    def query(self):
        return self.services["GoogleAdsService"].search.call_args.kwargs[
            "query"
        ]

    def google_ads_exception(self, message):
        error = MagicMock()
        error.message = message
        ex = GoogleAdsException(
            MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
        ex.failure = MagicMock(errors=[error])
        ex.request_id = "req-123"
        return ex


class TestStatusTools(MutateToolTestCase):

    def campaign_row(self, status="ENABLED"):
        return self.make_row(
            {
                "campaign.resource_name": "customers/123/campaigns/456",
                "campaign.name": "MBA 2027",
                "campaign.status": self.client.enums.CampaignStatusEnum[status],
            }
        )

    def test_set_campaign_status_only_validates_by_default(self):
        self.set_rows(self.campaign_row())

        result = mutate.set_campaign_status(
            customer_id="123", campaign_id="456", status="PAUSED"
        )

        request = self.sent_request("CampaignService", "mutate_campaigns")
        self.assertTrue(request.validate_only)
        self.assertEqual(request.customer_id, "123")
        operation = request.operations[0]
        self.assertEqual(
            operation.update.resource_name, "customers/123/campaigns/456"
        )
        self.assertEqual(operation.update.status.name, "PAUSED")
        self.assertEqual(list(operation.update_mask.paths), ["status"])
        self.assertFalse(result["applied"])
        self.assertIn("validate_only=false", result["message"])
        self.assertEqual(
            result["changes"][0]["status"], {"from": "ENABLED", "to": "PAUSED"}
        )
        self.assertEqual(result["changes"][0]["campaign"], "MBA 2027")

    def test_set_campaign_status_applies_when_not_validate_only(self):
        self.set_rows(self.campaign_row(status="PAUSED"))
        response = MagicMock()
        response.results = [
            MagicMock(resource_name="customers/123/campaigns/456")
        ]
        self.services["CampaignService"].mutate_campaigns.return_value = (
            response
        )

        result = mutate.set_campaign_status(
            customer_id="123-0",
            campaign_id=456,
            status="ENABLED",
            validate_only=False,
            login_customer_id="999",
        )

        request = self.sent_request("CampaignService", "mutate_campaigns")
        self.assertFalse(request.validate_only)
        self.assertEqual(request.customer_id, "1230")
        self.get_client.assert_called_once_with(login_customer_id="999")
        self.assertTrue(result["applied"])
        self.assertEqual(
            result["resource_names"], ["customers/123/campaigns/456"]
        )
        self.assertIn("WHERE campaign.id = 456", self.query())

    def test_set_campaign_status_not_found(self):
        self.set_rows()

        with self.assertRaises(ToolError) as context:
            mutate.set_campaign_status(
                customer_id="123", campaign_id="456", status="PAUSED"
            )

        self.assertIn("Campaign 456 was not found", str(context.exception))
        self.services["CampaignService"].mutate_campaigns.assert_not_called()

    def test_set_campaign_status_rejects_non_numeric_id(self):
        with self.assertRaises(ToolError):
            mutate.set_campaign_status(
                customer_id="123", campaign_id="abc", status="PAUSED"
            )
        self.services["GoogleAdsService"].search.assert_not_called()

    def test_set_campaign_status_api_error_becomes_tool_error(self):
        self.set_rows(self.campaign_row())
        self.services["CampaignService"].mutate_campaigns.side_effect = (
            self.google_ads_exception("Campaign is removed")
        )

        with self.assertRaises(ToolError) as context:
            mutate.set_campaign_status(
                customer_id="123", campaign_id="456", status="PAUSED"
            )

        self.assertIn(
            "Google Ads API Error: Campaign is removed", str(context.exception)
        )
        self.assertIn("Request ID: req-123", str(context.exception))

    def test_set_ad_group_status(self):
        self.set_rows(
            self.make_row(
                {
                    "ad_group.resource_name": "customers/123/adGroups/789",
                    "ad_group.name": "Brand",
                    "ad_group.status": self.client.enums.AdGroupStatusEnum.PAUSED,
                    "campaign.name": "MBA 2027",
                }
            )
        )

        result = mutate.set_ad_group_status(
            customer_id="123", ad_group_id="789", status="ENABLED"
        )

        operation = self.sent_request(
            "AdGroupService", "mutate_ad_groups"
        ).operations[0]
        self.assertEqual(
            operation.update.resource_name, "customers/123/adGroups/789"
        )
        self.assertEqual(operation.update.status.name, "ENABLED")
        self.assertEqual(list(operation.update_mask.paths), ["status"])
        self.assertEqual(
            result["changes"][0]["status"], {"from": "PAUSED", "to": "ENABLED"}
        )

    def test_set_ad_status(self):
        self.set_rows(
            self.make_row(
                {
                    "ad_group_ad.resource_name": "customers/123/adGroupAds/789~111",
                    "ad_group_ad.status": self.client.enums.AdGroupAdStatusEnum.ENABLED,
                    "ad_group_ad.ad.type_": self.client.enums.AdTypeEnum.RESPONSIVE_SEARCH_AD,
                    "ad_group.name": "Brand",
                }
            )
        )

        result = mutate.set_ad_status(
            customer_id="123", ad_group_id="789", ad_id="111", status="PAUSED"
        )

        operation = self.sent_request(
            "AdGroupAdService", "mutate_ad_group_ads"
        ).operations[0]
        self.assertEqual(
            operation.update.resource_name, "customers/123/adGroupAds/789~111"
        )
        self.assertEqual(operation.update.status.name, "PAUSED")
        self.assertIn("ad_group_ad.ad.id = 111", self.query())
        self.assertEqual(
            result["changes"][0]["ad_type"], "RESPONSIVE_SEARCH_AD"
        )


class TestUpdateCampaignBudget(MutateToolTestCase):

    def budget_row(
        self, amount_micros=10_000_000, shared=False, period="DAILY"
    ):
        return self.make_row(
            {
                "campaign.name": "MBA 2027",
                "campaign_budget.resource_name": "customers/123/campaignBudgets/55",
                "campaign_budget.amount_micros": amount_micros,
                "campaign_budget.period": self.client.enums.BudgetPeriodEnum[
                    period
                ],
                "campaign_budget.explicitly_shared": shared,
                "campaign_budget.reference_count": 3 if shared else 1,
                "customer.currency_code": "USD",
            }
        )

    def test_updates_amount_in_micros_rounded_to_cents(self):
        self.set_rows(self.budget_row())

        result = mutate.update_campaign_budget(
            customer_id="123", campaign_id="456", daily_amount=12.345
        )

        request = self.sent_request(
            "CampaignBudgetService", "mutate_campaign_budgets"
        )
        self.assertTrue(request.validate_only)
        operation = request.operations[0]
        self.assertEqual(
            operation.update.resource_name, "customers/123/campaignBudgets/55"
        )
        self.assertEqual(operation.update.amount_micros, 12_350_000)
        self.assertEqual(list(operation.update_mask.paths), ["amount_micros"])
        change = result["changes"][0]
        self.assertEqual(change["daily_amount"], {"from": 10.0, "to": 12.35})
        self.assertEqual(change["currency"], "USD")

    def test_rejects_increase_above_default_limit(self):
        self.set_rows(self.budget_row())

        with self.assertRaises(ToolError) as context:
            mutate.update_campaign_budget(
                customer_id="123", campaign_id="456", daily_amount=15.01
            )

        self.assertIn("50%", str(context.exception))
        self.assertIn(
            mutate.MAX_BUDGET_INCREASE_ENV_VAR, str(context.exception)
        )
        self.services[
            "CampaignBudgetService"
        ].mutate_campaign_budgets.assert_not_called()

    def test_allows_increase_at_limit(self):
        self.set_rows(self.budget_row())

        mutate.update_campaign_budget(
            customer_id="123", campaign_id="456", daily_amount=15
        )

        self.sent_request("CampaignBudgetService", "mutate_campaign_budgets")

    def test_limit_comes_from_environment(self):
        self.set_rows(self.budget_row())

        with patch.dict(
            os.environ, {mutate.MAX_BUDGET_INCREASE_ENV_VAR: "200"}
        ):
            mutate.update_campaign_budget(
                customer_id="123", campaign_id="456", daily_amount=30
            )

        self.sent_request("CampaignBudgetService", "mutate_campaign_budgets")

    def test_invalid_limit_in_environment(self):
        self.set_rows(self.budget_row())

        with patch.dict(
            os.environ, {mutate.MAX_BUDGET_INCREASE_ENV_VAR: "lots"}
        ):
            with self.assertRaises(ToolError):
                mutate.update_campaign_budget(
                    customer_id="123", campaign_id="456", daily_amount=11
                )

    def test_allows_large_decrease(self):
        self.set_rows(self.budget_row())

        mutate.update_campaign_budget(
            customer_id="123", campaign_id="456", daily_amount=1
        )

        self.sent_request("CampaignBudgetService", "mutate_campaign_budgets")

    def test_rejects_non_positive_amount(self):
        for amount in (0, -5, 0.001):
            with self.subTest(amount=amount):
                with self.assertRaises(ToolError):
                    mutate.update_campaign_budget(
                        customer_id="123",
                        campaign_id="456",
                        daily_amount=amount,
                    )
        self.services["GoogleAdsService"].search.assert_not_called()

    def test_shared_budget_requires_explicit_permission(self):
        self.set_rows(self.budget_row(shared=True))

        with self.assertRaises(ToolError) as context:
            mutate.update_campaign_budget(
                customer_id="123", campaign_id="456", daily_amount=11
            )
        self.assertIn("shared by 3 campaigns", str(context.exception))

        result = mutate.update_campaign_budget(
            customer_id="123",
            campaign_id="456",
            daily_amount=11,
            allow_shared_budget=True,
        )
        self.assertEqual(result["changes"][0]["shared_by_campaigns"], 3)

    def test_rejects_non_daily_budget(self):
        self.set_rows(self.budget_row(period="CUSTOM_PERIOD"))

        with self.assertRaises(ToolError) as context:
            mutate.update_campaign_budget(
                customer_id="123", campaign_id="456", daily_amount=11
            )

        self.assertIn("only daily budgets", str(context.exception))


class TestAddNegativeKeywords(MutateToolTestCase):

    def test_adds_campaign_negative_keywords(self):
        self.set_rows(
            self.make_row(
                {
                    "campaign.resource_name": "customers/123/campaigns/456",
                    "campaign.name": "MBA 2027",
                }
            )
        )

        result = mutate.add_negative_keywords(
            customer_id="123",
            campaign_id="456",
            keywords=["gratis", "  curso   gratis ", "GRATIS", ""],
            match_type="PHRASE",
        )

        request = self.sent_request(
            "CampaignCriterionService", "mutate_campaign_criteria"
        )
        self.assertTrue(request.validate_only)
        self.assertEqual(len(request.operations), 2)
        criterion = request.operations[0].create
        self.assertEqual(criterion.campaign, "customers/123/campaigns/456")
        self.assertTrue(criterion.negative)
        self.assertEqual(criterion.keyword.text, "gratis")
        self.assertEqual(criterion.keyword.match_type.name, "PHRASE")
        self.assertEqual(
            request.operations[1].create.keyword.text, "curso gratis"
        )
        change = result["changes"][0]
        self.assertEqual(change["level"], "campaign")
        self.assertEqual(
            change["negative_keywords_added"], ["gratis", "curso gratis"]
        )

    def test_adds_ad_group_negative_keywords(self):
        self.set_rows(
            self.make_row(
                {
                    "ad_group.resource_name": "customers/123/adGroups/789",
                    "ad_group.name": "Brand",
                    "campaign.name": "MBA 2027",
                }
            )
        )

        result = mutate.add_negative_keywords(
            customer_id="123",
            ad_group_id="789",
            keywords=["empleo"],
            match_type="EXACT",
        )

        request = self.sent_request(
            "AdGroupCriterionService", "mutate_ad_group_criteria"
        )
        criterion = request.operations[0].create
        self.assertEqual(criterion.ad_group, "customers/123/adGroups/789")
        self.assertTrue(criterion.negative)
        self.assertEqual(criterion.keyword.match_type.name, "EXACT")
        self.assertEqual(result["changes"][0]["level"], "ad_group")

    def test_requires_exactly_one_parent(self):
        for parents in ({}, {"campaign_id": "1", "ad_group_id": "2"}):
            with self.subTest(parents=parents):
                with self.assertRaises(ToolError):
                    mutate.add_negative_keywords(
                        customer_id="123",
                        keywords=["gratis"],
                        match_type="BROAD",
                        **parents,
                    )

    def test_rejects_empty_and_too_many_keywords(self):
        too_many = [
            f"kw{i}" for i in range(mutate.MAX_NEGATIVE_KEYWORDS_PER_CALL + 1)
        ]
        for keywords in ([], ["  "], too_many):
            with self.subTest(count=len(keywords)):
                with self.assertRaises(ToolError):
                    mutate.add_negative_keywords(
                        customer_id="123",
                        campaign_id="456",
                        keywords=keywords,
                        match_type="BROAD",
                    )
        self.services["GoogleAdsService"].search.assert_not_called()


class TestCpcBidTools(MutateToolTestCase):

    def ad_group_row(self, cpc_bid_micros=1_000_000, strategy="MANUAL_CPC"):
        return self.make_row(
            {
                "ad_group.resource_name": "customers/123/adGroups/789",
                "ad_group.name": "Brand",
                "ad_group.cpc_bid_micros": cpc_bid_micros,
                "campaign.name": "MBA 2027",
                "campaign.bidding_strategy_type": self.client.enums.BiddingStrategyTypeEnum[
                    strategy
                ],
                "customer.currency_code": "USD",
            }
        )

    def keyword_row(self, cpc_bid_micros=0, negative=False):
        return self.make_row(
            {
                "ad_group_criterion.resource_name": "customers/123/adGroupCriteria/789~42",
                "ad_group_criterion.keyword.text": "mba online",
                "ad_group_criterion.keyword.match_type": self.client.enums.KeywordMatchTypeEnum.PHRASE,
                "ad_group_criterion.negative": negative,
                "ad_group_criterion.cpc_bid_micros": cpc_bid_micros,
                "ad_group_criterion.effective_cpc_bid_micros": 2_000_000,
                "ad_group.name": "Brand",
                "campaign.bidding_strategy_type": self.client.enums.BiddingStrategyTypeEnum.MANUAL_CPC,
                "customer.currency_code": "USD",
            }
        )

    def test_set_ad_group_cpc_bid(self):
        self.set_rows(self.ad_group_row())

        result = mutate.set_ad_group_cpc_bid(
            customer_id="123", ad_group_id="789", cpc_bid=1.25
        )

        operation = self.sent_request(
            "AdGroupService", "mutate_ad_groups"
        ).operations[0]
        self.assertEqual(operation.update.cpc_bid_micros, 1_250_000)
        self.assertEqual(list(operation.update_mask.paths), ["cpc_bid_micros"])
        self.assertEqual(
            result["changes"][0]["cpc_bid"], {"from": 1.0, "to": 1.25}
        )
        self.assertNotIn("warnings", result)

    def test_set_ad_group_cpc_bid_warns_for_automated_bidding(self):
        self.set_rows(self.ad_group_row(strategy="MAXIMIZE_CONVERSIONS"))

        result = mutate.set_ad_group_cpc_bid(
            customer_id="123", ad_group_id="789", cpc_bid=1.25
        )

        self.assertIn("MAXIMIZE_CONVERSIONS", result["warnings"][0])

    def test_set_ad_group_cpc_bid_rejects_increase_above_limit(self):
        self.set_rows(self.ad_group_row())

        with self.assertRaises(ToolError) as context:
            mutate.set_ad_group_cpc_bid(
                customer_id="123", ad_group_id="789", cpc_bid=2
            )

        self.assertIn(mutate.MAX_BID_INCREASE_ENV_VAR, str(context.exception))

    def test_set_keyword_cpc_bid_uses_inherited_bid_as_baseline(self):
        self.set_rows(self.keyword_row())

        with self.assertRaises(ToolError):
            mutate.set_keyword_cpc_bid(
                customer_id="123",
                ad_group_id="789",
                criterion_id="42",
                cpc_bid=3.5,
            )

        result = mutate.set_keyword_cpc_bid(
            customer_id="123", ad_group_id="789", criterion_id="42", cpc_bid=3
        )

        request = self.sent_request(
            "AdGroupCriterionService", "mutate_ad_group_criteria"
        )
        operation = request.operations[0]
        self.assertEqual(
            operation.update.resource_name,
            "customers/123/adGroupCriteria/789~42",
        )
        self.assertEqual(operation.update.cpc_bid_micros, 3_000_000)
        change = result["changes"][0]
        self.assertTrue(change["bid_was_inherited_from_ad_group"])
        self.assertEqual(change["cpc_bid"], {"from": 2.0, "to": 3.0})
        self.assertEqual(change["match_type"], "PHRASE")
        self.assertIn("ad_group_criterion.type = 'KEYWORD'", self.query())

    def test_set_keyword_cpc_bid_rejects_negative_keyword(self):
        self.set_rows(self.keyword_row(negative=True))

        with self.assertRaises(ToolError) as context:
            mutate.set_keyword_cpc_bid(
                customer_id="123",
                ad_group_id="789",
                criterion_id="42",
                cpc_bid=1,
            )

        self.assertIn("negative keyword", str(context.exception))


class TestMutateToolsMounting(unittest.IsolatedAsyncioTestCase):
    """Verifies that the mutate tools are only exposed when enabled."""

    async def list_tools(self, config_file):
        config = ToolsConfig.load(
            str(importlib.resources.files("ads_mcp").joinpath(config_file))
        )
        parent = FastMCP("Test Parent")
        with patch("ads_mcp.config.ToolsConfig.load", return_value=config):
            initialize_and_mount_tools(parent)
        return await parent.list_tools()

    async def test_disabled_in_default_config(self):
        tool_names = [
            t.name for t in await self.list_tools("tools_config.yaml")
        ]

        self.assertIn("search_search", tool_names)
        for name in MUTATE_TOOL_NAMES:
            self.assertNotIn(name, tool_names)

    async def test_disabled_without_config(self):
        self.assertFalse(ToolsConfig().is_namespace_enabled("mutate"))

    async def test_enabled_in_write_config(self):
        tools = {
            t.name: t for t in await self.list_tools("tools_config_write.yaml")
        }

        self.assertIn("search_search", tools)
        for name in MUTATE_TOOL_NAMES:
            self.assertIn(name, tools)
            self.assertFalse(tools[name].annotations.read_only_hint)
            properties = tools[name].parameters["properties"]
            self.assertIs(properties["validate_only"]["default"], True)
            for param_name, param_schema in properties.items():
                if param_schema.get("default", "") is None:
                    self.assertIn(
                        {"type": "null"},
                        param_schema.get("anyOf", []),
                        f"{name}.{param_name} must allow null",
                    )


if __name__ == "__main__":
    unittest.main()
