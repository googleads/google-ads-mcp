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

"""Performance Max campaign + asset group tools.

Performance Max is Google's ML-driven campaign type that serves across Search,
Display, YouTube, Discover, Gmail, and Maps. It needs:

  1. A Campaign with advertising_channel_type=PERFORMANCE_MAX and a bidding
     strategy (MaxConversions / MaxConversionValue, typically with a target
     CPA or target ROAS).
  2. One or more AssetGroups — each contains creative assets (headlines,
     descriptions, images, videos, logos, business name) plus optional
     audience signals and listing group filters.

Recommended flow for an LLM:
  1. create_campaign_budget(...)
  2. create_performance_max_campaign(..., status='PAUSED')
  3. create_image_asset(...) x3 (landscape, square, logo), returning resource_names
  4. create_pmax_asset_group(..., final_urls=[...], headlines=[...],
     long_headlines=[...], descriptions=[...], business_name=...,
     landscape_image_asset_resource_names=[...],
     square_image_asset_resource_names=[...],
     logo_asset_resource_names=[...])
  5. enable_campaign(...) when ready.
"""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_performance_max_campaign(
    customer_id: str,
    name: str,
    budget_id: str,
    bidding_strategy_type: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
    url_expansion_opt_out: bool = False,
    status: str = "PAUSED",
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Performance Max campaign.

    Defaults to PAUSED so you can add an asset group before serving.

    Args:
        customer_id: 10-digit customer id.
        name: Campaign name (unique).
        budget_id: Numeric campaign_budget id (create with create_campaign_budget).
        bidding_strategy_type: 'MAXIMIZE_CONVERSIONS' (optionally with target_cpa_micros),
            'MAXIMIZE_CONVERSION_VALUE' (optionally with target_roas).
            PMax doesn't support MANUAL_CPC / TARGET_CPA / TARGET_ROAS as standalone — you
            set the target inside MaxConversions/MaxConversionValue.
        target_cpa_micros: Target CPA in micros (only for MAXIMIZE_CONVERSIONS).
        target_roas: Target ROAS ratio (only for MAXIMIZE_CONVERSION_VALUE).
        url_expansion_opt_out: True to prevent Google from serving to URLs
            beyond your final_urls list.
        status: 'PAUSED' (default) or 'ENABLED'.
        start_date: YYYY-MM-DD.
        end_date: YYYY-MM-DD.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.status = client.enums.CampaignStatusEnum[status]
    c.advertising_channel_type = (
        client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    )
    c.campaign_budget = _common.campaign_budget_path(customer_id, budget_id)
    c.url_expansion_opt_out = bool(url_expansion_opt_out)

    # Assigning an instance (not just touching) is required to set a
    # proto-plus oneof branch. Touching `c.maximize_conversions` without
    # mutating a sub-field leaves the oneof unset and the API rejects it.
    bs = bidding_strategy_type.upper()
    if bs == "MAXIMIZE_CONVERSIONS":
        mc = client.get_type("MaximizeConversions")
        if target_cpa_micros is not None:
            mc.target_cpa_micros = int(target_cpa_micros)
        c.maximize_conversions = mc
    elif bs == "MAXIMIZE_CONVERSION_VALUE":
        mcv = client.get_type("MaximizeConversionValue")
        if target_roas is not None:
            mcv.target_roas = float(target_roas)
        c.maximize_conversion_value = mcv
    else:
        raise ValueError(
            "Performance Max only supports MAXIMIZE_CONVERSIONS or "
            "MAXIMIZE_CONVERSION_VALUE. Use target_cpa_micros / target_roas "
            "to set targets."
        )

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
        "note": (
            "Campaign created PAUSED. Add an asset group via "
            "create_pmax_asset_group(...) before enabling."
        ),
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_pmax_asset_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    final_urls: list[str],
    headlines: list[str],
    long_headlines: list[str],
    descriptions: list[str],
    business_name: str,
    landscape_image_asset_resource_names: list[str],
    square_image_asset_resource_names: list[str],
    logo_asset_resource_names: list[str],
    portrait_image_asset_resource_names: list[str] | None = None,
    youtube_video_asset_resource_names: list[str] | None = None,
    call_to_action: str | None = None,
    status: str = "PAUSED",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Performance Max AssetGroup inside an existing PMax campaign.

    This uses the Google Ads temp-resource pattern: text assets are created
    inline (temp resource names < 0), image assets must already exist (pass
    their resource_names from create_image_asset). The server assembles the
    whole mutate in one atomic call so if any asset fails, nothing is created.

    Minimum requirements (Google rejects asset groups that don't meet these):
      - 3+ headlines (each <= 30 chars)
      - 1+ long_headlines (each <= 90 chars)
      - 2+ descriptions (each <= 90 chars; at least one <= 60 chars for short slot)
      - business_name (<= 25 chars)
      - 1+ landscape image (1200x628, <= 5MB)
      - 1+ square image (1200x1200, <= 5MB)
      - 1+ logo image (1200x1200, <= 5MB)

    Args:
        customer_id: 10-digit customer id.
        campaign_id: Numeric PMax campaign id.
        name: Asset group name.
        final_urls: Landing page URLs (at least 1).
        headlines: 3-15 short headlines.
        long_headlines: 1-5 long headlines.
        descriptions: 2-5 descriptions.
        business_name: The advertiser name that appears in the ad.
        landscape_image_asset_resource_names: 1+ pre-created landscape image assets.
        square_image_asset_resource_names: 1+ pre-created square image assets.
        logo_asset_resource_names: 1+ pre-created logo assets.
        portrait_image_asset_resource_names: Optional portrait (960x1200) images.
        youtube_video_asset_resource_names: Optional YouTube video assets.
        call_to_action: Optional CTA text ('Shop now', 'Sign up', etc.).
        status: 'PAUSED' (default) or 'ENABLED'.
        dry_run: If True, runs validate_only.
    """
    if len(headlines) < 3:
        raise ValueError("PMax asset groups need at least 3 headlines.")
    if len(long_headlines) < 1:
        raise ValueError("PMax asset groups need at least 1 long_headline.")
    if len(descriptions) < 2:
        raise ValueError("PMax asset groups need at least 2 descriptions.")
    if not landscape_image_asset_resource_names:
        raise ValueError("Need at least 1 landscape image asset.")
    if not square_image_asset_resource_names:
        raise ValueError("Need at least 1 square image asset.")
    if not logo_asset_resource_names:
        raise ValueError("Need at least 1 logo asset.")

    client = utils.get_googleads_client()
    google_ads_service = client.get_service("GoogleAdsService")

    # Temp resource-name counter (negative numbers per the Google Ads docs).
    temp_id = -1

    def next_temp() -> int:
        nonlocal temp_id
        val = temp_id
        temp_id -= 1
        return val

    mutate_operations = []

    # 1) AssetGroup create
    ag_temp = next_temp()
    ag_resource = f"customers/{customer_id}/assetGroups/{ag_temp}"
    ag_op = client.get_type("MutateOperation")
    ag = ag_op.asset_group_operation.create
    ag.resource_name = ag_resource
    ag.name = name
    ag.campaign = _common.campaign_path(customer_id, campaign_id)
    ag.final_urls.extend(final_urls)
    ag.status = client.enums.AssetGroupStatusEnum[status]
    mutate_operations.append(ag_op)

    def _add_text_asset(text: str, field_type_name: str) -> None:
        asset_temp = next_temp()
        asset_resource = f"customers/{customer_id}/assets/{asset_temp}"

        # Create the Asset
        asset_op = client.get_type("MutateOperation")
        a = asset_op.asset_operation.create
        a.resource_name = asset_resource
        a.text_asset.text = text
        mutate_operations.append(asset_op)

        # Link it to the asset group
        link_op = client.get_type("MutateOperation")
        link = link_op.asset_group_asset_operation.create
        link.asset_group = ag_resource
        link.asset = asset_resource
        link.field_type = client.enums.AssetFieldTypeEnum[field_type_name]
        mutate_operations.append(link_op)

    def _link_existing_asset(asset_rn: str, field_type_name: str) -> None:
        link_op = client.get_type("MutateOperation")
        link = link_op.asset_group_asset_operation.create
        link.asset_group = ag_resource
        link.asset = asset_rn
        link.field_type = client.enums.AssetFieldTypeEnum[field_type_name]
        mutate_operations.append(link_op)

    # 2) Text assets (create inline)
    for h in headlines:
        _add_text_asset(h, "HEADLINE")
    for lh in long_headlines:
        _add_text_asset(lh, "LONG_HEADLINE")
    for d in descriptions:
        _add_text_asset(d, "DESCRIPTION")
    _add_text_asset(business_name, "BUSINESS_NAME")
    if call_to_action:
        _add_text_asset(call_to_action, "CALL_TO_ACTION_SELECTION")

    # 3) Image + video assets (already exist; just link)
    for rn in landscape_image_asset_resource_names:
        _link_existing_asset(rn, "MARKETING_IMAGE")
    for rn in square_image_asset_resource_names:
        _link_existing_asset(rn, "SQUARE_MARKETING_IMAGE")
    for rn in logo_asset_resource_names:
        _link_existing_asset(rn, "LOGO")
    for rn in portrait_image_asset_resource_names or []:
        _link_existing_asset(rn, "PORTRAIT_MARKETING_IMAGE")
    for rn in youtube_video_asset_resource_names or []:
        _link_existing_asset(rn, "YOUTUBE_VIDEO")

    with _common.google_ads_errors():
        response = google_ads_service.mutate(
            request=_common.build_request(
                client, "MutateGoogleAdsRequest",
                customer_id=customer_id,
                mutate_operations=mutate_operations,
                validate_only=dry_run,
            )
        )

    # Pull out the AssetGroup result (always first)
    ag_result = None
    for r in response.mutate_operation_responses:
        if r._pb.HasField("asset_group_result"):
            ag_result = r.asset_group_result.resource_name
            break

    return {
        "dry_run": dry_run,
        "asset_group_resource_name": ag_result,
        "operations_count": len(mutate_operations),
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_pmax_asset_groups(
    customer_id: str,
    campaign_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Lists Performance Max asset groups, optionally scoped to a campaign."""
    where = []
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = (
        "SELECT asset_group.id, asset_group.name, asset_group.status, "
        "asset_group.final_urls, asset_group.campaign, asset_group.resource_name "
        f"FROM asset_group{clause} LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)
