"""Offline safety/contract tests with real Google Ads protobuf schemas."""

import concurrent.futures
from datetime import date
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastmcp.exceptions import ToolError
from google.auth.credentials import AnonymousCredentials
from google.ads.googleads.client import GoogleAdsClient

from ads_mcp.extensions import changes as ch, search as s

CID = "1234567890"


def fake_query(cid, resource, fields, where, login=None):
    if resource == "customer":
        return [{"customer.currency_code": "COP", "customer.manager": False}]
    if "resource_name =" not in where:
        return []
    rn = re.search("resource_name = '([^']+)'", where)[1]
    defaults = dict(
        name="Existing",
        status="PAUSED",
        campaign=f"customers/{CID}/campaigns/1",
        campaign_budget=f"customers/{CID}/campaignBudgets/1",
        advertising_channel_type="SEARCH",
        bidding_strategy_type="MANUAL_CPC",
        negative=False,
        **{
            "keyword.text": "existing",
            "keyword.match_type": "EXACT",
            "ad.type": "RESPONSIVE_SEARCH_AD",
        },
    )
    defaults["type"] = {
        "ad_group": "SEARCH_STANDARD",
        "shared_set": "NEGATIVE_KEYWORDS",
        "campaign_criterion": "LOCATION",
    }.get(resource, "KEYWORD")
    return [
        {
            f: (
                rn
                if f.endswith(".resource_name")
                else defaults.get(f[len(resource) + 1 :], "")
            )
            for f in fields
        }
    ]


class EditingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = GoogleAdsClient(
            credentials=AnonymousCredentials(), use_proto_plus=True
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "plans.db"
        self.env = patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_PROPOSALS_DB": str(self.db),
                "GOOGLE_ADS_MCP_ACCOUNT_LIMITS": "{}",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.query = patch.object(ch, "query", side_effect=fake_query)
        self.query.start()
        self.addCleanup(self.query.stop)
        self.requests = []

        def mutate(cid, operations, login, validate_only):
            request = self.client.get_type(
                "MutateGoogleAdsRequest", version="v25"
            )
            request.customer_id = cid
            request.mutate_operations = operations
            request.validate_only = validate_only
            request.partial_failure = False
            self.requests.append(request)
            return self.client.get_type("MutateGoogleAdsResponse")

        self.mutate = patch.object(ch, "mutate", side_effect=mutate).start()
        self.addCleanup(patch.stopall)

    def build(self, model, builder):
        return s.prepare(CID, None, model, builder)

    def test_real_sdk_accepts_all_creation_strategies_and_dates(self):
        for strategy in (
            "MANUAL_CPC",
            "MAXIMIZE_CLICKS",
            "MAXIMIZE_CONVERSIONS",
            "MAXIMIZE_CONVERSION_VALUE",
        ):
            with self.subTest(strategy=strategy):
                plan = self.build(
                    s.Campaign(
                        action="create",
                        name="Test",
                        daily_budget="20000.123456",
                        bidding=strategy,
                        start_date=date(2026, 11, 1),
                        end_date=date(2026, 12, 1),
                        contains_eu_political_advertising=False,
                    ),
                    s.campaign,
                )
                self.assertEqual(plan["state"], "PREPARED")
                operation = (
                    self.requests[-1]
                    .mutate_operations[-1]
                    .campaign_operation.create
                )
                self.assertEqual(operation.status.name, "PAUSED")
                self.assertEqual(
                    operation.start_date_time, "2026-11-01 00:00:00"
                )
                self.assertTrue(self.requests[-1].validate_only)

    def test_real_sdk_accepts_each_domain(self):
        cases = [
            (
                s.Budget(action="create", name="Budget", daily_amount="100"),
                s.budget,
            ),
            (
                s.Budget(action="update", budget_id="1", daily_amount="101"),
                s.budget,
            ),
            (
                s.Campaign(
                    action="update",
                    campaign_id="1",
                    name="New",
                    end_date=date(2026, 12, 1),
                ),
                s.campaign,
            ),
            (
                s.Campaign(action="status", campaign_id="1", status="ENABLED"),
                s.campaign,
            ),
            (
                s.Campaign(
                    action="add_targeting",
                    campaign_id="1",
                    location_ids=["2826"],
                    language_ids=["1000"],
                ),
                s.campaign,
            ),
            (
                s.Campaign(
                    action="remove_targeting",
                    campaign_id="1",
                    criterion_ids=["2"],
                ),
                s.campaign,
            ),
            (
                s.AdGroup(
                    action="create",
                    campaign_id="1",
                    name="Group",
                    cpc_bid="1.25",
                ),
                s.ad_group,
            ),
            (
                s.AdGroup(
                    action="update",
                    ad_group_id="1",
                    name="Group2",
                    cpc_bid="2.5",
                ),
                s.ad_group,
            ),
            (
                s.AdGroup(action="status", ad_group_id="1", status="PAUSED"),
                s.ad_group,
            ),
            (
                s.Ad(
                    action="create",
                    ad_group_id="1",
                    headlines=["One", "Two", "Three"],
                    descriptions=["First", "Second"],
                    final_urls=["https://example.com"],
                ),
                s.ad,
            ),
            (
                s.Ad(
                    action="update",
                    ad_group_id="1",
                    ad_id="2",
                    headlines=["Four", "Five", "Six"],
                    path1="test",
                ),
                s.ad,
            ),
            (
                s.Ad(
                    action="status",
                    ad_group_id="1",
                    ad_id="2",
                    status="REMOVED",
                ),
                s.ad,
            ),
            (
                s.Keywords(
                    action="add",
                    ad_group_id="1",
                    keywords=[
                        s.Keyword(text="test", match_type="EXACT", cpc_bid="1")
                    ],
                ),
                s.keywords,
            ),
            (
                s.Keywords(
                    action="status",
                    ad_group_id="1",
                    criterion_ids=["2"],
                    status="PAUSED",
                ),
                s.keywords,
            ),
            (
                s.Keywords(
                    action="update",
                    ad_group_id="1",
                    criterion_ids=["2"],
                    cpc_bid="2",
                ),
                s.keywords,
            ),
            (
                s.Keywords(
                    action="add_negatives",
                    campaign_id="1",
                    keywords=[s.Keyword(text="free", match_type="PHRASE")],
                ),
                s.keywords,
            ),
            (
                s.Keywords(
                    action="add_negatives",
                    ad_group_id="1",
                    keywords=[s.Keyword(text="free", match_type="EXACT")],
                ),
                s.keywords,
            ),
            (
                s.NegativeList(
                    action="create",
                    name="Exclusions",
                    keywords=[s.Keyword(text="free", match_type="EXACT")],
                    campaign_ids=["1"],
                ),
                s.negative_list,
            ),
            (
                s.NegativeList(action="rename", list_id="1", name="Other"),
                s.negative_list,
            ),
            (
                s.NegativeList(
                    action="add",
                    list_id="1",
                    keywords=[s.Keyword(text="cheap", match_type="BROAD")],
                ),
                s.negative_list,
            ),
            (
                s.NegativeList(
                    action="remove_terms", list_id="1", criterion_ids=["2"]
                ),
                s.negative_list,
            ),
            (
                s.NegativeList(
                    action="attach", list_id="1", campaign_ids=["1"]
                ),
                s.negative_list,
            ),
            (
                s.NegativeList(
                    action="detach", list_id="1", campaign_ids=["1"]
                ),
                s.negative_list,
            ),
            (s.NegativeList(action="remove", list_id="1"), s.negative_list),
        ]
        for model, builder in cases:
            with self.subTest(model=model):
                self.build(model, builder)
        self.assertTrue(all(r.validate_only for r in self.requests))

    def test_exact_money_rejects_invalid_values(self):
        self.assertEqual(ch.money("0.000001"), 1)
        self.assertEqual(ch.money("123.123456"), 123123456)
        for value in ("NaN", "Infinity", "-1", "0", "1.0000001", "1e40"):
            with self.subTest(value=value), self.assertRaises(ToolError):
                ch.money(value)

    def test_bad_ids_and_mcc_rejected(self):
        for value in ("123' OR 1=1", "123", "0000000000"):
            with self.assertRaises(ToolError):
                s.Build(value)
        with self.assertRaises(ToolError):
            s.Build(CID, "1")

    def test_duplicates_and_invalid_rsa_rejected_before_validation(self):
        with self.assertRaises(ToolError):
            self.build(
                s.Keywords(
                    action="add",
                    ad_group_id="1",
                    keywords=[
                        s.Keyword(text="Same", match_type="EXACT"),
                        s.Keyword(text="same", match_type="EXACT"),
                    ],
                ),
                s.keywords,
            )
        with self.assertRaises(ToolError):
            self.build(
                s.Ad(
                    action="create",
                    ad_group_id="1",
                    headlines=["x"],
                    descriptions=["x"],
                    final_urls=["javascript:alert(1)"],
                ),
                s.ad,
            )
        self.mutate.assert_not_called()

    def test_irrelevant_fields_rejected(self):
        with self.assertRaises(ToolError):
            self.build(
                s.Campaign(
                    action="status",
                    campaign_id="1",
                    status="PAUSED",
                    daily_budget="50",
                ),
                s.campaign,
            )
        self.mutate.assert_not_called()

    def test_limit_currency_and_budget_are_account_specific(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_ACCOUNT_LIMITS": json.dumps(
                    {CID: {"currency_code": "USD", "daily_budget": "500"}}
                )
            },
        ):
            with self.assertRaises(ToolError):
                self.build(
                    s.Budget(action="create", name="B", daily_amount="1"),
                    s.budget,
                )
        with patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_ACCOUNT_LIMITS": json.dumps(
                    {CID: {"currency_code": "COP", "daily_budget": "500"}}
                )
            },
        ):
            with self.assertRaises(ToolError):
                self.build(
                    s.Budget(action="create", name="B", daily_amount="501"),
                    s.budget,
                )
        self.mutate.assert_not_called()

    def proposal(self):
        return self.build(
            s.Budget(action="update", budget_id="1", daily_amount="100"),
            s.budget,
        )["plan_id"]

    def test_confirmation_and_cancel_never_write(self):
        plan_id = self.proposal()
        self.mutate.reset_mock()
        with self.assertRaises(ToolError):
            ch.apply(plan_id, False)
        ch.Store().transition(plan_id, "PREPARED", "CANCELLED")
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)
        self.mutate.assert_not_called()

    def test_snapshot_change_rejects_apply(self):
        plan_id = self.proposal()
        with patch.object(ch, "reread", return_value=[]):
            with self.assertRaises(ToolError):
                ch.apply(plan_id, True)
        self.assertEqual(ch.Store().get(plan_id)["state"], "REJECTED")
        self.assertTrue(all(r.validate_only for r in self.requests))

    def test_network_timeout_stays_uncertain_and_non_retryable(self):
        plan_id = self.proposal()
        original = self.mutate.side_effect

        def timeout(cid, ops, login, validate_only):
            if not validate_only:
                raise TimeoutError()
            return original(cid, ops, login, validate_only)

        self.mutate.side_effect = timeout
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)
        self.assertEqual(ch.Store().get(plan_id)["state"], "UNKNOWN")
        before = self.mutate.call_count
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)
        self.assertEqual(self.mutate.call_count, before)

    def test_verification_failure_never_reports_applied(self):
        plan_id = self.proposal()
        with patch.object(
            ch, "verify", side_effect=RuntimeError("read failed")
        ):
            result = ch.apply(plan_id, True)
        self.assertEqual(result["state"], "UNVERIFIED")

    def test_success_is_not_reexecuted(self):
        plan_id = self.proposal()
        with patch.object(ch, "verify", return_value={"verified": True}):
            result = ch.apply(plan_id, True)
        self.assertEqual(result["state"], "APPLIED")
        count = self.mutate.call_count
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)
        self.assertEqual(self.mutate.call_count, count)

    def test_sqlite_claim_is_atomic(self):
        plan_id = self.proposal()

        def claim():
            try:
                ch.Store().transition(plan_id, "PREPARED", "CHECKING")
                return True
            except ToolError:
                return False

        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            self.assertEqual(sum(pool.map(lambda _: claim(), range(4))), 1)

    def test_tampered_proposal_rejected(self):
        plan_id = self.proposal()
        with ch.Store(self.db).connect() as db:
            db.execute("UPDATE proposals SET body='{}' WHERE id=?", (plan_id,))
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)

    def test_verify_checks_values_not_only_existence(self):
        body = dict(
            customer_id=CID,
            login_customer_id=None,
            operations=[],
            checks=[
                dict(
                    resource="campaign",
                    resource_name=f"customers/{CID}/campaigns/1",
                    expected={"campaign.name": "Changed"},
                )
            ],
        )
        self.assertFalse(ch.verify(body, [])["verified"])

    def test_validation_failure_does_not_save_a_proposal(self):
        self.mutate.side_effect = ToolError("Google validation failed")
        with self.assertRaises(ToolError):
            self.proposal()
        with ch.Store().connect() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM proposals").fetchone()[0], 0
            )

    def test_expired_proposal_never_dispatches(self):
        plan_id = self.proposal()
        with ch.Store().connect() as db:
            db.execute("UPDATE proposals SET created=0 WHERE id=?", (plan_id,))
        self.mutate.reset_mock()
        with self.assertRaises(ToolError):
            ch.apply(plan_id, True)
        self.mutate.assert_not_called()

    def test_manual_bid_guard_rejects_automated_bidding(self):
        def automated(*args, **kwargs):
            rows = fake_query(*args, **kwargs)
            for row in rows:
                if "campaign.bidding_strategy_type" in row:
                    row["campaign.bidding_strategy_type"] = (
                        "MAXIMIZE_CONVERSIONS"
                    )
            return rows

        with patch.object(ch, "query", side_effect=automated):
            with self.assertRaises(ToolError):
                self.build(
                    s.AdGroup(action="update", ad_group_id="1", cpc_bid="5"),
                    s.ad_group,
                )
        self.mutate.assert_not_called()

    def test_response_ids_survive_failed_post_read(self):
        plan_id = self.proposal()
        response = self.client.get_type("MutateGoogleAdsResponse")
        response.mutate_operation_responses = [
            {
                "campaign_budget_result": {
                    "resource_name": f"customers/{CID}/campaignBudgets/1"
                }
            }
        ]
        original = self.mutate.side_effect
        self.mutate.side_effect = lambda cid, ops, login, validate: (
            original(cid, ops, login, validate) if validate else response
        )
        with patch.object(ch, "verify", side_effect=TimeoutError()):
            result = ch.apply(plan_id, True)
        self.assertEqual(result["state"], "UNVERIFIED")
        self.assertEqual(
            result["result"]["resource_names"],
            [f"customers/{CID}/campaignBudgets/1"],
        )

    def test_reconcile_never_writes_or_unlocks(self):
        plan_id = self.proposal()
        ch.Store().transition(plan_id, "PREPARED", "UNKNOWN")
        self.mutate.reset_mock()
        ch.reconcile(plan_id)
        self.assertEqual(ch.Store().get(plan_id)["state"], "UNKNOWN")
        self.mutate.assert_not_called()

    def test_negative_removal_is_a_typed_remove_operation(self):
        def negative(*args, **kwargs):
            rows = fake_query(*args, **kwargs)
            for row in rows:
                if "ad_group_criterion.negative" in row:
                    row["ad_group_criterion.negative"] = True
            return rows

        with patch.object(ch, "query", side_effect=negative):
            self.build(
                s.Keywords(
                    action="remove_negatives",
                    ad_group_id="1",
                    criterion_ids=["2"],
                ),
                s.keywords,
            )
        self.assertTrue(
            self.requests[-1]
            .mutate_operations[0]
            .ad_group_criterion_operation.remove.endswith("1~2")
        )


class EditingMountTest(unittest.IsolatedAsyncioTestCase):
    async def test_editing_is_opt_in_and_read_contracts_unchanged(self):
        from fastmcp import FastMCP
        from ads_mcp.coordinator import initialize_and_mount_tools
        from ads_mcp.config import ToolsConfig

        with patch.object(
            ToolsConfig,
            "load",
            return_value=ToolsConfig(
                {
                    "namespaces": {
                        "customers": True,
                        "search": True,
                        "metadata": True,
                        "editing": True,
                    }
                }
            ),
        ):
            server = FastMCP("Editing test")
            initialize_and_mount_tools(server)
        tools = {t.name: t for t in await server.list_tools()}
        self.assertIn("search_search", tools)
        self.assertIn("editing_prepare_campaign", tools)
        self.assertFalse(
            tools["editing_apply_proposal"].annotations.readOnlyHint
        )
        self.assertFalse(
            tools["editing_apply_proposal"].parameters["properties"][
                "confirmed"
            ]["default"]
        )
        with patch.object(ToolsConfig, "load", return_value=ToolsConfig()):
            server = FastMCP("Read test")
            initialize_and_mount_tools(server)
        self.assertEqual(
            {t.name for t in await server.list_tools()},
            {
                "customers_list_accessible_customers",
                "search_search",
                "metadata_get_resource_metadata",
            },
        )


class GatewayTest(unittest.TestCase):
    def test_reserved_type_field_is_read_with_real_protobuf(self):
        from unittest.mock import Mock

        client = GoogleAdsClient(
            credentials=AnonymousCredentials(), use_proto_plus=True
        )
        row = client.get_type("GoogleAdsRow", version="v25")
        row.ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
        service = Mock()
        service.search.return_value = [row]
        with patch.object(ch, "service", return_value=service):
            rows = ch.query(CID, "ad_group", ["ad_group.type"], "", limit=1)
        self.assertEqual(rows, [{"ad_group.type": "SEARCH_STANDARD"}])
        self.assertIsNone(service.search.call_args.kwargs["retry"])
        self.assertEqual(service.search.call_args.kwargs["timeout"], 30)

    def test_gateway_writes_have_no_automatic_retry(self):
        from unittest.mock import Mock

        gateway = Mock()
        with patch.object(ch, "service", return_value=gateway):
            ch.mutate(CID, [], None, True)
        call = gateway.mutate.call_args.kwargs
        self.assertTrue(call["request"]["validate_only"])
        self.assertFalse(call["request"]["partial_failure"])
        self.assertIsNone(call["retry"])

    def test_local_entry_rejects_shared_oauth_mode(self):
        from ads_mcp.extensions.local import run

        with patch.dict(
            os.environ, {"GOOGLE_ADS_MCP_OAUTH_CLIENT_ID": "example"}
        ):
            with self.assertRaises(RuntimeError):
                run()
