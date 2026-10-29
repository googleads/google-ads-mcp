"""Typed Search operations. Builders never dispatch writes directly."""

from datetime import date
import os
from typing import Literal

from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field

from . import changes as ch


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


Status = Literal["PAUSED", "ENABLED", "REMOVED"]
Match = Literal["EXACT", "PHRASE", "BROAD"]


class Campaign(Input):
    action: Literal[
        "create", "update", "status", "add_targeting", "remove_targeting"
    ]
    campaign_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    budget_id: str | None = None
    daily_budget: str | None = None
    bidding: (
        Literal[
            "MANUAL_CPC",
            "MAXIMIZE_CLICKS",
            "MAXIMIZE_CONVERSIONS",
            "MAXIMIZE_CONVERSION_VALUE",
        ]
        | None
    ) = None
    max_cpc: str | None = None
    target_cpa: str | None = None
    target_roas: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: Status | None = None
    location_ids: list[str] = Field(default_factory=list)
    language_ids: list[str] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    location_mode: Literal["PRESENCE", "PRESENCE_OR_INTEREST"] | None = None
    contains_eu_political_advertising: bool | None = None


class Budget(Input):
    action: Literal["create", "update"]
    budget_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    daily_amount: str


class AdGroup(Input):
    action: Literal["create", "update", "status"]
    campaign_id: str | None = None
    ad_group_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    cpc_bid: str | None = None
    status: Status | None = None


class Ad(Input):
    action: Literal["create", "update", "status"]
    ad_group_id: str
    ad_id: str | None = None
    headlines: list[str] | None = None
    descriptions: list[str] | None = None
    final_urls: list[str] | None = None
    path1: str | None = Field(default=None, max_length=15)
    path2: str | None = Field(default=None, max_length=15)
    status: Status | None = None


class Keyword(Input):
    text: str = Field(min_length=1, max_length=80)
    match_type: Match
    cpc_bid: str | None = None


class Keywords(Input):
    action: Literal[
        "add", "update", "status", "add_negatives", "remove_negatives"
    ]
    campaign_id: str | None = None
    ad_group_id: str | None = None
    criterion_ids: list[str] = Field(default_factory=list)
    keywords: list[Keyword] = Field(default_factory=list)
    cpc_bid: str | None = None
    status: Status | None = None


class NegativeList(Input):
    action: Literal[
        "create", "rename", "add", "remove_terms", "attach", "detach", "remove"
    ]
    list_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    keywords: list[Keyword] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    campaign_ids: list[str] = Field(default_factory=list)


FIELDS = {
    "campaign": [
        "name",
        "status",
        "campaign_budget",
        "advertising_channel_type",
        "start_date_time",
        "end_date_time",
        "bidding_strategy_type",
        "geo_target_type_setting.positive_geo_target_type",
    ],
    "campaign_budget": ["name", "amount_micros", "explicitly_shared", "status"],
    "ad_group": ["name", "status", "campaign", "cpc_bid_micros", "type"],
    "ad_group_ad": [
        "status",
        "ad.id",
        "ad.final_urls",
        "ad.responsive_search_ad.headlines",
        "ad.responsive_search_ad.descriptions",
        "ad.responsive_search_ad.path1",
        "ad.responsive_search_ad.path2",
        "ad.type",
    ],
    "ad_group_criterion": [
        "status",
        "negative",
        "keyword.text",
        "keyword.match_type",
        "cpc_bid_micros",
    ],
    "campaign_criterion": [
        "negative",
        "type",
        "keyword.text",
        "keyword.match_type",
        "location.geo_target_constant",
        "language.language_constant",
    ],
    "shared_set": ["name", "status", "type"],
    "shared_criterion": ["shared_set", "keyword.text", "keyword.match_type"],
    "campaign_shared_set": ["campaign", "shared_set", "status"],
}
COLLECTIONS = {
    "campaign": "campaigns",
    "campaign_budget": "campaignBudgets",
    "ad_group": "adGroups",
    "ad_group_ad": "adGroupAds",
    "ad": "ads",
    "ad_group_criterion": "adGroupCriteria",
    "campaign_criterion": "campaignCriteria",
    "shared_set": "sharedSets",
    "shared_criterion": "sharedCriteria",
    "campaign_shared_set": "campaignSharedSets",
}


def required(value, name):
    if value is None or value == [] or value == "":
        raise ToolError(f"{name} is required for this action.")
    return value


def flatten(data, prefix):
    result = {}
    for key, value in data.items():
        if key == "resource_name":
            continue
        path = f"{prefix}.{key.removesuffix('_')}"
        if isinstance(value, dict):
            result.update(flatten(value, path))
        else:
            result[path] = value
    return result


def allowed(model, fields):
    extra = model.model_fields_set - set(fields) - {"action"}
    if extra:
        raise ToolError(
            f"Fields not applicable to this action: {sorted(extra)}"
        )


def keyword_values(keywords, negative=False):
    seen = set()
    values = []
    for item in required(keywords, "keywords"):
        text = item.text.strip()
        if not text:
            raise ToolError("Keyword text cannot be blank.")
        key = (text.casefold(), item.match_type)
        if key in seen:
            raise ToolError("Duplicate keyword/match type in proposal.")
        seen.add(key)
        if negative and item.cpc_bid is not None:
            raise ToolError("Negative keywords cannot have bids.")
        data = dict(keyword=dict(text=text, match_type=item.match_type))
        if item.cpc_bid is not None:
            data["cpc_bid_micros"] = ch.money(item.cpc_bid)
        values.append(data)
    return values


class Build:
    def __init__(self, cid, login=None):
        self.cid = ch.customer(cid)
        resolved_login = login or os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        self.login = ch.customer(resolved_login) if resolved_login else None
        self.ops, self.watches, self.checks = [], [], []
        rows = ch.query(
            self.cid,
            "customer",
            ["customer.currency_code", "customer.manager"],
            f"customer.id = {self.cid}",
            self.login,
        )
        if len(rows) != 1 or rows[0]["customer.manager"]:
            raise ToolError(
                "Select an advertising client account, not a manager."
            )
        self.currency = rows[0]["customer.currency_code"]
        self.track(
            "customer",
            f"customer.id = {self.cid}",
            ["customer.currency_code", "customer.manager"],
        )

    def rn(self, resource, *ids):
        return f"customers/{self.cid}/{COLLECTIONS[resource]}/" + "~".join(
            ch.identifier(i) for i in ids
        )

    def track(self, resource, where, fields=None, exists=False):
        fields = fields or [f"{resource}.resource_name"] + [
            f"{resource}.{f}" for f in FIELDS[resource]
        ]
        item = ch.watch(self.cid, resource, fields, where, self.login)
        if exists and len(item["before"]) != 1:
            raise ToolError(f"{resource} not found, removed or inaccessible.")
        self.watches.append(item)
        return item["before"]

    def entity(self, resource, *ids):
        rn = self.rn(resource, *ids)
        rows = self.track(
            resource, f"{resource}.resource_name = '{rn}'", exists=True
        )
        return rn, rows[0]

    def search_campaign(self, campaign_id):
        rn, row = self.entity("campaign", campaign_id)
        if row["campaign.advertising_channel_type"] != "SEARCH":
            raise ToolError("Only Search campaigns are supported.")
        return rn, row

    def search_group(self, group_id):
        rn, row = self.entity("ad_group", group_id)
        campaign_id = row["ad_group.campaign"].rsplit("/", 1)[1]
        _, campaign = self.search_campaign(campaign_id)
        if row["ad_group.type"] != "SEARCH_STANDARD":
            raise ToolError("Only standard Search ad groups are supported.")
        return rn, campaign

    def manual(self, campaign):
        if campaign["campaign.bidding_strategy_type"] != "MANUAL_CPC":
            raise ToolError("CPC edits require a MANUAL_CPC campaign.")

    def add(
        self, resource, action, data, expected=None, read_resource=None, rn=None
    ):
        if action == "update" and data.get("status") == "REMOVED":
            action, data = "remove", data["resource_name"]
            expected = {}
        operation = {action: data}
        if action == "update":
            operation["update_mask"] = {
                "paths": [
                    key[len(resource) + 1 :] for key in flatten(data, resource)
                ]
            }
        index = len(self.ops)
        self.ops.append({f"{resource}_operation": operation})
        target = read_resource or resource
        if expected is None:
            expected = flatten(data, target) if isinstance(data, dict) else {}
        self.checks.append(
            dict(
                resource=target,
                expected=expected,
                resource_name=rn,
                operation_index=index,
                removed=action == "remove"
                or (isinstance(data, dict) and data.get("status") == "REMOVED"),
            )
        )

    def finish(self, action):
        return ch.prepare(
            self.cid,
            self.login,
            action,
            self.ops,
            self.watches,
            self.currency,
            self.checks,
        )


def campaign(b, p):
    if p.action == "create":
        allowed(
            p,
            {
                "name",
                "budget_id",
                "daily_budget",
                "bidding",
                "max_cpc",
                "target_cpa",
                "target_roas",
                "start_date",
                "end_date",
                "location_mode",
                "contains_eu_political_advertising",
            },
        )
        name = required(p.name, "name")
        strategy = required(p.bidding, "bidding")
        political = required(
            p.contains_eu_political_advertising,
            "contains_eu_political_advertising",
        )
        if (p.budget_id is None) == (p.daily_budget is None):
            raise ToolError("Provide exactly one of budget_id or daily_budget.")
        if p.budget_id:
            budget_rn, _ = b.entity("campaign_budget", p.budget_id)
        else:
            budget_rn = f"customers/{b.cid}/campaignBudgets/-1"
            b.add(
                "campaign_budget",
                "create",
                dict(
                    resource_name=budget_rn,
                    name=f"{name} budget",
                    amount_micros=ch.money(p.daily_budget),
                    delivery_method="STANDARD",
                    explicitly_shared=False,
                ),
            )
        data = dict(
            name=name,
            status="PAUSED",
            advertising_channel_type="SEARCH",
            network_settings=dict(
                target_google_search=True,
                target_search_network=False,
                target_content_network=False,
            ),
            campaign_budget=budget_rn,
            contains_eu_political_advertising=(
                "CONTAINS_EU_POLITICAL_ADVERTISING"
                if political
                else "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
            ),
            geo_target_type_setting=dict(
                positive_geo_target_type=p.location_mode or "PRESENCE"
            ),
        )
        if p.max_cpc is not None and strategy != "MAXIMIZE_CLICKS":
            raise ToolError("max_cpc is supported only for MAXIMIZE_CLICKS.")
        if p.target_cpa is not None and strategy != "MAXIMIZE_CONVERSIONS":
            raise ToolError("target_cpa requires MAXIMIZE_CONVERSIONS.")
        if (
            p.target_roas is not None
            and strategy != "MAXIMIZE_CONVERSION_VALUE"
        ):
            raise ToolError("target_roas requires MAXIMIZE_CONVERSION_VALUE.")
        if strategy == "MANUAL_CPC":
            data["manual_cpc"] = {}
        elif strategy == "MAXIMIZE_CLICKS":
            data["target_spend"] = (
                {"cpc_bid_ceiling_micros": ch.money(p.max_cpc)}
                if p.max_cpc
                else {}
            )
        elif strategy == "MAXIMIZE_CONVERSIONS":
            data["maximize_conversions"] = (
                {"target_cpa_micros": ch.money(p.target_cpa)}
                if p.target_cpa
                else {}
            )
        else:
            data["maximize_conversion_value"] = (
                {"target_roas": ch.money(p.target_roas) / 1_000_000}
                if p.target_roas
                else {}
            )
        for key in ("start_date", "end_date"):
            if getattr(p, key):
                data[key + "_time"] = getattr(p, key).isoformat() + (
                    " 00:00:00" if key == "start_date" else " 23:59:59"
                )
        if p.end_date and p.start_date and p.end_date < p.start_date:
            raise ToolError("end_date precedes start_date.")
        # New parent IDs are resolved by Google within this atomic request.
        expected = flatten(data, "campaign")
        expected["campaign.bidding_strategy_type"] = (
            "TARGET_SPEND" if strategy == "MAXIMIZE_CLICKS" else strategy
        )
        b.add("campaign", "create", data, expected)
        return
    rn, _ = b.search_campaign(required(p.campaign_id, "campaign_id"))
    if p.action == "update":
        allowed(
            p,
            {"campaign_id", "name", "start_date", "end_date", "location_mode"},
        )
        data = {"resource_name": rn}
        for field in ("name", "start_date", "end_date"):
            val = getattr(p, field)
            if val is not None:
                if isinstance(val, date):
                    data[field + "_time"] = val.isoformat() + (
                        " 00:00:00" if field == "start_date" else " 23:59:59"
                    )
                else:
                    data[field] = val
        if p.location_mode:
            data["geo_target_type_setting"] = dict(
                positive_geo_target_type=p.location_mode
            )
        if len(data) == 1:
            raise ToolError("No fields to update.")
        b.add("campaign", "update", data, rn=rn)
    elif p.action == "status":
        allowed(p, {"campaign_id", "status"})
        status = required(p.status, "status")
        b.add(
            "campaign", "update", dict(resource_name=rn, status=status), rn=rn
        )
    else:
        allowed(
            p,
            (
                {"campaign_id", "location_ids", "language_ids"}
                if p.action == "add_targeting"
                else {"campaign_id", "criterion_ids"}
            ),
        )
        b.track("campaign_criterion", f"campaign_criterion.campaign = '{rn}'")
        if p.action == "remove_targeting":
            for criterion_id in required(p.criterion_ids, "criterion_ids"):
                crn, row = b.entity(
                    "campaign_criterion", p.campaign_id, criterion_id
                )
                if row["campaign_criterion.type"] not in (
                    "LOCATION",
                    "LANGUAGE",
                ):
                    raise ToolError(
                        "Only location/language criteria may be removed here."
                    )
                b.add("campaign_criterion", "remove", crn, rn=crn)
        else:
            if not p.location_ids and not p.language_ids:
                raise ToolError("Supply location_ids or language_ids.")
            for key, ids, collection in [
                ("location", p.location_ids, "geoTargetConstants"),
                ("language", p.language_ids, "languageConstants"),
            ]:
                for target in ids:
                    field = (
                        "geo_target_constant"
                        if key == "location"
                        else "language_constant"
                    )
                    data = dict(
                        campaign=rn,
                        **{
                            key: {
                                field: f"{collection}/{ch.identifier(target)}"
                            }
                        },
                    )
                    b.add(
                        "campaign_criterion",
                        "create",
                        data,
                        {f"campaign_criterion.{key}.{field}": data[key][field]},
                    )


def budget(b, p):
    amount = ch.money(p.daily_amount)
    if p.action == "create":
        allowed(p, {"name", "daily_amount"})
        b.add(
            "campaign_budget",
            "create",
            dict(
                name=required(p.name, "name"),
                amount_micros=amount,
                delivery_method="STANDARD",
                explicitly_shared=False,
            ),
        )
    else:
        allowed(p, {"budget_id", "name", "daily_amount"})
        rn, _ = b.entity("campaign_budget", required(p.budget_id, "budget_id"))
        campaigns = b.track("campaign", f"campaign.campaign_budget = '{rn}'")
        if any(
            r["campaign.advertising_channel_type"] != "SEARCH"
            for r in campaigns
        ):
            raise ToolError(
                "Budget affects non-Search campaigns; outside v1 scope."
            )
        data = dict(resource_name=rn, amount_micros=amount)
        if p.name:
            data["name"] = p.name
        b.add("campaign_budget", "update", data, rn=rn)


def ad_group(b, p):
    if p.action == "create":
        allowed(p, {"campaign_id", "name", "cpc_bid"})
        crn, parent = b.search_campaign(required(p.campaign_id, "campaign_id"))
        data = dict(
            campaign=crn,
            name=required(p.name, "name"),
            status="PAUSED",
            type_="SEARCH_STANDARD",
        )
        if p.cpc_bid:
            b.manual(parent)
            data["cpc_bid_micros"] = ch.money(p.cpc_bid)
        b.add(
            "ad_group",
            "create",
            data,
            {
                "ad_group.name": data["name"],
                "ad_group.status": "PAUSED",
                "ad_group.campaign": crn,
            },
        )
    else:
        rn, parent = b.search_group(required(p.ad_group_id, "ad_group_id"))
        allowed(
            p,
            (
                {"ad_group_id", "status"}
                if p.action == "status"
                else {"ad_group_id", "name", "cpc_bid"}
            ),
        )
        data = dict(resource_name=rn)
        if p.action == "status":
            data["status"] = required(p.status, "status")
        else:
            if p.name:
                data["name"] = p.name
            if p.cpc_bid:
                b.manual(parent)
                data["cpc_bid_micros"] = ch.money(p.cpc_bid)
            if len(data) == 1:
                raise ToolError("No fields to update.")
        b.add("ad_group", "update", data, rn=rn)


def _rsa(p):
    result = {}
    for field, minimum, maximum, length in [
        ("headlines", 3, 15, 30),
        ("descriptions", 2, 4, 90),
    ]:
        values = getattr(p, field)
        if values is not None:
            if not minimum <= len(values) <= maximum or any(
                not s.strip() or len(s) > length for s in values
            ):
                raise ToolError(
                    f"Invalid {field}: {minimum}-{maximum} nonempty texts, max {length} characters."
                )
            result[field] = [dict(text=s) for s in values]
    for field in ("path1", "path2"):
        if getattr(p, field) is not None:
            result[field] = getattr(p, field)
    if p.final_urls is not None:
        from urllib.parse import urlparse

        if not p.final_urls or any(
            urlparse(u).scheme not in ("https", "http")
            or not urlparse(u).netloc
            for u in p.final_urls
        ):
            raise ToolError("final_urls must contain valid HTTP(S) URLs.")
    return result


def ad(b, p):
    group, _ = b.search_group(p.ad_group_id)
    if p.action == "status":
        allowed(p, {"ad_group_id", "ad_id", "status"})
        rn, row = b.entity(
            "ad_group_ad", p.ad_group_id, required(p.ad_id, "ad_id")
        )
        if row["ad_group_ad.ad.type"] != "RESPONSIVE_SEARCH_AD":
            raise ToolError("Only responsive Search ads are supported.")
        b.add(
            "ad_group_ad",
            "update",
            dict(resource_name=rn, status=required(p.status, "status")),
            rn=rn,
        )
        return
    allowed(
        p,
        {
            "ad_group_id",
            "ad_id",
            "headlines",
            "descriptions",
            "final_urls",
            "path1",
            "path2",
        }
        - ({"ad_id"} if p.action == "create" else set()),
    )
    rsa = _rsa(p)
    data = {}
    if rsa:
        data["responsive_search_ad"] = rsa
    if p.final_urls is not None:
        data["final_urls"] = p.final_urls
    expected = {
        f"ad_group_ad.ad.responsive_search_ad.{k}": v for k, v in rsa.items()
    }
    if p.final_urls is not None:
        expected["ad_group_ad.ad.final_urls"] = p.final_urls
    if p.action == "create":
        required(p.headlines, "headlines")
        required(p.descriptions, "descriptions")
        required(p.final_urls, "final_urls")
        expected["ad_group_ad.status"] = "PAUSED"
        b.add(
            "ad_group_ad",
            "create",
            dict(ad_group=group, status="PAUSED", ad=data),
            expected,
        )
    else:
        rn, row = b.entity(
            "ad_group_ad", p.ad_group_id, required(p.ad_id, "ad_id")
        )
        if row["ad_group_ad.ad.type"] != "RESPONSIVE_SEARCH_AD":
            raise ToolError("Only responsive Search ads are supported.")
        if not data:
            raise ToolError("No fields to update.")
        data["resource_name"] = b.rn("ad", p.ad_id)
        b.add("ad", "update", data, expected, "ad_group_ad", rn)
        # Nested field masks must select leaves, not the whole ad subtype.
        paths = [f"responsive_search_ad.{k}" for k in rsa]
        if p.final_urls is not None:
            paths.append("final_urls")
        b.ops[-1]["ad_operation"]["update_mask"]["paths"] = paths


def keywords(b, p):
    if bool(p.campaign_id) == bool(p.ad_group_id):
        raise ToolError("Provide exactly one of campaign_id or ad_group_id.")
    if p.ad_group_id:
        parent, campaign_row = b.search_group(p.ad_group_id)
        resource, id_value = "ad_group_criterion", p.ad_group_id
        parent_field = "ad_group"
    else:
        parent, campaign_row = b.search_campaign(p.campaign_id)
        resource, id_value = "campaign_criterion", p.campaign_id
        parent_field = "campaign"
        if p.action not in ("add_negatives", "remove_negatives"):
            raise ToolError("Positive keywords require an ad group.")
    negative = p.action in ("add_negatives", "remove_negatives")
    b.track(resource, f"{resource}.{parent_field} = '{parent}'")
    if p.action in ("add", "add_negatives"):
        allowed(p, {"campaign_id", "ad_group_id", "keywords"})
        for data in keyword_values(p.keywords, negative):
            if "cpc_bid_micros" in data:
                b.manual(campaign_row)
            data.update({parent_field: parent, "negative": negative})
            if not negative:
                data["status"] = "PAUSED"
            b.add(
                resource,
                "create",
                data,
                {
                    f"{resource}.keyword.text": data["keyword"]["text"],
                    f"{resource}.keyword.match_type": data["keyword"][
                        "match_type"
                    ],
                    f"{resource}.negative": negative,
                    **(
                        {f"{resource}.status": "PAUSED"} if not negative else {}
                    ),
                },
            )
    else:
        allowed(
            p,
            {"campaign_id", "ad_group_id", "criterion_ids"}
            | (
                {"status"}
                if p.action == "status"
                else {"cpc_bid"} if p.action == "update" else set()
            ),
        )
        for criterion_id in required(p.criterion_ids, "criterion_ids"):
            rn, row = b.entity(resource, id_value, criterion_id)
            if row[f"{resource}.negative"] != negative:
                raise ToolError(
                    "Criterion negative/positive type differs from action."
                )
            if not row[f"{resource}.keyword.text"]:
                raise ToolError("Selected criterion is not a keyword.")
            if p.action == "remove_negatives":
                b.add(resource, "remove", rn, rn=rn)
            else:
                data = dict(resource_name=rn)
                if p.action == "status":
                    data["status"] = required(p.status, "status")
                else:
                    b.manual(campaign_row)
                    data["cpc_bid_micros"] = ch.money(
                        required(p.cpc_bid, "cpc_bid")
                    )
                b.add(resource, "update", data, rn=rn)


def negative_list(b, p):
    if p.action == "create":
        allowed(p, {"name", "keywords", "campaign_ids"})
        rn = f"customers/{b.cid}/sharedSets/-1"
        b.add(
            "shared_set",
            "create",
            dict(
                resource_name=rn,
                name=required(p.name, "name"),
                type_="NEGATIVE_KEYWORDS",
            ),
            {"shared_set.name": p.name, "shared_set.type": "NEGATIVE_KEYWORDS"},
        )
    else:
        rn, row = b.entity("shared_set", required(p.list_id, "list_id"))
        if row["shared_set.type"] != "NEGATIVE_KEYWORDS":
            raise ToolError(
                "Selected shared set is not a negative keyword list."
            )
        b.track("shared_criterion", f"shared_criterion.shared_set = '{rn}'")
        b.track(
            "campaign_shared_set", f"campaign_shared_set.shared_set = '{rn}'"
        )
    if p.action in ("create", "add"):
        if p.action == "add":
            allowed(p, {"list_id", "keywords"})
            required(p.keywords, "keywords")
        for data in keyword_values(p.keywords, True) if p.keywords else []:
            data["shared_set"] = rn
            b.add(
                "shared_criterion",
                "create",
                data,
                {
                    "shared_criterion.keyword.text": data["keyword"]["text"],
                    "shared_criterion.keyword.match_type": data["keyword"][
                        "match_type"
                    ],
                },
            )
    if p.action in ("create", "attach", "detach"):
        if p.action != "create":
            allowed(p, {"list_id", "campaign_ids"})
            required(p.campaign_ids, "campaign_ids")
        for campaign_id in p.campaign_ids:
            crn, _ = b.search_campaign(campaign_id)
            b.track(
                "campaign_shared_set", f"campaign_shared_set.campaign = '{crn}'"
            )
            if p.action == "detach":
                link, _ = b.entity(
                    "campaign_shared_set", campaign_id, p.list_id
                )
                b.add("campaign_shared_set", "remove", link, rn=link)
            else:
                b.add(
                    "campaign_shared_set",
                    "create",
                    dict(campaign=crn, shared_set=rn),
                    {"campaign_shared_set.campaign": crn},
                )
    elif p.action == "rename":
        allowed(p, {"list_id", "name"})
        b.add(
            "shared_set",
            "update",
            dict(resource_name=rn, name=required(p.name, "name")),
            rn=rn,
        )
    elif p.action == "remove_terms":
        allowed(p, {"list_id", "criterion_ids"})
        for criterion_id in required(p.criterion_ids, "criterion_ids"):
            krn, _ = b.entity("shared_criterion", p.list_id, criterion_id)
            b.add("shared_criterion", "remove", krn, rn=krn)
    elif p.action == "remove":
        allowed(p, {"list_id"})
        links = b.watches[-1]["before"]
        if any(r.get("campaign_shared_set.status") == "ENABLED" for r in links):
            raise ToolError(
                "Detach this list from campaigns before removing it."
            )
        b.add("shared_set", "remove", rn, rn=rn)


def prepare(cid, login, model, builder):
    b = Build(cid, login)
    builder(b, model)
    return b.finish(f"{model.__class__.__name__}:{model.action}")
