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

"""Tools for managing Campaign resources."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common

_BASE_FIELDS = (
    "campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
    "campaign.advertising_channel_sub_type, campaign.start_date, campaign.end_date, "
    "campaign.bidding_strategy_type, campaign.campaign_budget, "
    "campaign.serving_status, campaign.resource_name"
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_campaigns(
    customer_id: str,
    status_filter: list[str] | None = None,
    channel_type_filter: list[str] | None = None,
    name_contains: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Lists campaigns in the account.

    Args:
        customer_id: 10-digit customer id.
        status_filter: Optional list e.g. ['ENABLED','PAUSED','REMOVED'].
        channel_type_filter: Optional list e.g. ['SEARCH','DISPLAY','PERFORMANCE_MAX','SHOPPING','VIDEO','DEMAND_GEN','LOCAL','LOCAL_SERVICES','MULTI_CHANNEL'].
        name_contains: Optional substring filter on campaign.name.
        limit: Max rows.
    """
    where = []
    if status_filter:
        where.append(f"campaign.status IN ({_common.comma_join(status_filter)})")
    if channel_type_filter:
        where.append(
            f"campaign.advertising_channel_type IN ({_common.comma_join(channel_type_filter)})"
        )
    if name_contains:
        safe = name_contains.replace("'", "\\'")
        where.append(f"campaign.name LIKE '%{safe}%'")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = f"SELECT {_BASE_FIELDS} FROM campaign{clause} LIMIT {int(limit)}"
    return _common.gaql_search(customer_id, query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_campaign(customer_id: str, campaign_id: str) -> list[dict[str, Any]]:
    """Returns one campaign by id."""
    query = (
        f"SELECT {_BASE_FIELDS} FROM campaign "
        f"WHERE campaign.id = {int(campaign_id)} LIMIT 1"
    )
    return _common.gaql_search(customer_id, query)


def _set_status(
    customer_id: str, campaign_id: str, status: str, dry_run: bool
) -> dict[str, Any]:
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = _common.campaign_path(customer_id, campaign_id)
    op.update.status = client.enums.CampaignStatusEnum[status]
    _common.set_field_mask(op, "status")
    with _common.google_ads_errors():
        response = service.mutate_campaigns(
            request=_common.build_request(
                client, "MutateCampaignsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "status": status,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def pause_campaign(
    customer_id: str, campaign_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Sets a campaign to PAUSED."""
    return _set_status(customer_id, campaign_id, "PAUSED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True)
)
def enable_campaign(
    customer_id: str, campaign_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Sets a campaign to ENABLED."""
    return _set_status(customer_id, campaign_id, "ENABLED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def remove_campaign(
    customer_id: str, campaign_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Removes (deletes) a campaign. Irreversible — campaign moves to REMOVED status."""
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.remove = _common.campaign_path(customer_id, campaign_id)
    with _common.google_ads_errors():
        response = service.mutate_campaigns(
            request=_common.build_request(
                client, "MutateCampaignsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def update_campaign(
    customer_id: str,
    campaign_id: str,
    name: str | None = None,
    status: str | None = None,
    budget_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates assignable fields on a campaign. Only provided fields change.

    Args:
        customer_id: 10-digit customer id.
        campaign_id: Numeric campaign id.
        name: New name.
        status: 'ENABLED' / 'PAUSED' / 'REMOVED'.
        budget_id: Numeric campaign_budget id to attach.
        start_date: YYYY-MM-DD.
        end_date: YYYY-MM-DD.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = _common.campaign_path(customer_id, campaign_id)

    if name is not None:
        op.update.name = name
        _common.set_field_mask(op, "name")
    if status is not None:
        op.update.status = client.enums.CampaignStatusEnum[status]
        _common.set_field_mask(op, "status")
    if budget_id is not None:
        op.update.campaign_budget = _common.campaign_budget_path(
            customer_id, budget_id
        )
        _common.set_field_mask(op, "campaign_budget")
    if start_date is not None:
        op.update.start_date = start_date
        _common.set_field_mask(op, "start_date")
    if end_date is not None:
        op.update.end_date = end_date
        _common.set_field_mask(op, "end_date")

    if not op.update_mask.paths:
        return {"dry_run": dry_run, "results": [], "note": "no fields to update"}

    with _common.google_ads_errors():
        response = service.mutate_campaigns(
            request=_common.build_request(
                client, "MutateCampaignsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_search_campaign(
    customer_id: str,
    name: str,
    budget_id: str,
    bidding_strategy_type: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
    manual_cpc_enhanced: bool | None = None,
    status: str = "PAUSED",
    start_date: str | None = None,
    end_date: str | None = None,
    network_search: bool = True,
    network_search_partners: bool = False,
    network_content: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Search campaign.

    By default the campaign is created PAUSED so the LLM has to enable it explicitly.

    Args:
        customer_id: 10-digit customer id.
        name: Campaign name (must be unique).
        budget_id: Numeric campaign_budget id (create one first via create_campaign_budget).
        bidding_strategy_type: One of 'MAXIMIZE_CONVERSIONS', 'MAXIMIZE_CONVERSION_VALUE',
            'TARGET_CPA', 'TARGET_ROAS', 'MANUAL_CPC'.
        target_cpa_micros: Required if bidding_strategy_type == 'TARGET_CPA'.
        target_roas: Required if bidding_strategy_type == 'TARGET_ROAS'. Ratio (e.g. 4.0 = 400%).
        manual_cpc_enhanced: For MANUAL_CPC, whether to enable enhanced CPC.
        status: 'PAUSED' or 'ENABLED'. Defaults to PAUSED.
        start_date: YYYY-MM-DD.
        end_date: YYYY-MM-DD.
        network_search: Include Google Search results.
        network_search_partners: Include Search Partners.
        network_content: Include Display Network.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")

    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.status = client.enums.CampaignStatusEnum[status]
    c.advertising_channel_type = (
        client.enums.AdvertisingChannelTypeEnum.SEARCH
    )
    c.campaign_budget = _common.campaign_budget_path(customer_id, budget_id)

    bs = bidding_strategy_type.upper()
    if bs == "MAXIMIZE_CONVERSIONS":
        # Assigning an empty MaximizeConversions instance marks the oneof.
        # Simply accessing `c.maximize_conversions` is a no-op in proto-plus.
        mc = client.get_type("MaximizeConversions")
        if target_cpa_micros is not None:
            mc.target_cpa_micros = int(target_cpa_micros)
        c.maximize_conversions = mc
    elif bs == "MAXIMIZE_CONVERSION_VALUE":
        mcv = client.get_type("MaximizeConversionValue")
        if target_roas is not None:
            mcv.target_roas = float(target_roas)
        c.maximize_conversion_value = mcv
    elif bs == "TARGET_CPA":
        if target_cpa_micros is None:
            raise ValueError("target_cpa_micros is required for TARGET_CPA")
        tcpa = client.get_type("TargetCpa")
        tcpa.target_cpa_micros = int(target_cpa_micros)
        c.target_cpa = tcpa
    elif bs == "TARGET_ROAS":
        if target_roas is None:
            raise ValueError("target_roas is required for TARGET_ROAS")
        tr = client.get_type("TargetRoas")
        tr.target_roas = float(target_roas)
        c.target_roas = tr
    elif bs == "MANUAL_CPC":
        mcpc = client.get_type("ManualCpc")
        if manual_cpc_enhanced is not None:
            mcpc.enhanced_cpc_enabled = bool(manual_cpc_enhanced)
        c.manual_cpc = mcpc
    else:
        raise ValueError(f"Unsupported bidding_strategy_type {bidding_strategy_type}")

    c.network_settings.target_google_search = network_search
    c.network_settings.target_search_network = network_search_partners
    c.network_settings.target_content_network = network_content
    c.network_settings.target_partner_search_network = False

    if start_date:
        c.start_date = start_date
    if end_date:
        c.end_date = end_date

    with _common.google_ads_errors():
        response = service.mutate_campaigns(
            request=_common.build_request(
                client, "MutateCampaignsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
