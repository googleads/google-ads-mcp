# Copyright 2026 ReBattery.
# SPDX-License-Identifier: Apache-2.0

"""Write tools for creating safely paused Google Ads campaign drafts."""

from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils


campaigns_mcp = FastMCP("campaigns")


def _customer_id(value: str) -> str:
    normalized = value.replace("-", "").strip()
    if not normalized.isdigit():
        raise ValueError("customer_id must contain digits only.")
    return normalized


def _resource_name(response: Any, kind: str) -> str:
    results = getattr(response, "results", None) or []
    if not results or not getattr(results[0], "resource_name", None):
        raise RuntimeError(f"Google Ads did not return a {kind} resource name.")
    return results[0].resource_name


@campaigns_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def create_search_campaign_draft(
    customer_id: str,
    name: str,
    final_url: str,
    headlines: list[str],
    descriptions: list[str],
    keywords: list[str],
    daily_budget_micros: int,
    geo_target_constant_ids: list[str] | None = None,
    ad_group_name: str | None = None,
) -> dict[str, Any]:
    """Create a complete Search campaign in PAUSED status.

    This creates a budget, campaign, ad group, responsive search ad, broad-match
    keywords, and optional geo targets. It never enables the campaign or starts
    serving ads. Review the returned resource names before a separate activation
    action is introduced.
    """
    customer_id = _customer_id(customer_id)
    if not name.strip() or not final_url.strip():
        raise ValueError("name and final_url are required.")
    if daily_budget_micros <= 0:
        raise ValueError("daily_budget_micros must be positive.")
    if not 3 <= len(headlines) <= 15:
        raise ValueError("Responsive Search Ads require 3 to 15 headlines.")
    if not 2 <= len(descriptions) <= 4:
        raise ValueError("Responsive Search Ads require 2 to 4 descriptions.")
    if not keywords:
        raise ValueError("At least one keyword is required.")

    client = utils.get_googleads_client()

    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.create
    budget.name = f"{name.strip()} budget"
    budget.amount_micros = daily_budget_micros
    budget.delivery_method = "STANDARD"
    budget.explicitly_shared = False
    budget_service = client.get_service("CampaignBudgetService")
    budget_name = _resource_name(
        budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_operation]
        ),
        "campaign budget",
    )

    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = name.strip()
    campaign.status = "PAUSED"
    campaign.advertising_channel_type = "SEARCH"
    campaign.campaign_budget = budget_name
    campaign.manual_cpc.enhanced_cpc_enabled = False
    campaign_service = client.get_service("CampaignService")
    campaign_name = _resource_name(
        campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        ),
        "campaign",
    )

    group_operation = client.get_type("AdGroupOperation")
    group = group_operation.create
    group.name = ad_group_name.strip() if ad_group_name else f"{name.strip()} ad group"
    group.campaign = campaign_name
    group.status = "PAUSED"
    group.type_ = "SEARCH_STANDARD"
    ad_group_service = client.get_service("AdGroupService")
    group_name = _resource_name(
        ad_group_service.mutate_ad_groups(
            customer_id=customer_id, operations=[group_operation]
        ),
        "ad group",
    )

    ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_operation.create
    ad_group_ad.ad_group = group_name
    ad_group_ad.status = "PAUSED"
    ad_group_ad.ad.final_urls.append(final_url.strip())
    for headline in headlines:
        ad_group_ad.ad.responsive_search_ad.headlines.append(
            client.get_type("AdTextAsset")(text=headline.strip())
        )
    for description in descriptions:
        ad_group_ad.ad.responsive_search_ad.descriptions.append(
            client.get_type("AdTextAsset")(text=description.strip())
        )
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_name = _resource_name(
        ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[ad_operation]
        ),
        "ad",
    )

    criterion_operations = []
    for keyword in keywords:
        if not keyword.strip():
            continue
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.create
        criterion.ad_group = group_name
        criterion.status = "PAUSED"
        criterion.keyword.text = keyword.strip()
        criterion.keyword.match_type = "BROAD"
        criterion_operations.append(operation)
    if not criterion_operations:
        raise ValueError("keywords must include at least one non-empty value.")
    criterion_service = client.get_service("AdGroupCriterionService")
    criterion_response = criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=criterion_operations
    )

    location_count = 0
    if geo_target_constant_ids:
        location_operations = []
        for geo_id in geo_target_constant_ids:
            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = campaign_name
            criterion.location.geo_target_constant = f"geoTargetConstants/{geo_id}"
            location_operations.append(operation)
        if location_operations:
            client.get_service("CampaignCriterionService").mutate_campaign_criteria(
                customer_id=customer_id, operations=location_operations
            )
            location_count = len(location_operations)

    return {
        "status": "PAUSED_DRAFT",
        "campaign": campaign_name,
        "budget": budget_name,
        "ad_group": group_name,
        "ad": ad_name,
        "keyword_count": len(criterion_response.results),
        "geo_target_count": location_count,
    }
