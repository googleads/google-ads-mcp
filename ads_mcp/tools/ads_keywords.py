# Copyright 2025 Google LLC.
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

"""Tools for creating ads and keywords via the MCP server."""

from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import Context
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    headlines: List[str],
    descriptions: List[str],
    final_url: str,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    status: str = "ENABLED",
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a responsive search ad in an ad group.

    Responsive search ads allow you to provide multiple headlines and descriptions,
    and Google Ads will automatically test different combinations.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group to add the ad to.
        headlines: List of headline texts (min 3, max 15). Each headline max 30 characters.
        descriptions: List of description texts (min 2, max 4). Each description max 90 characters.
        final_url: The landing page URL for the ad.
        path1: First URL path text (max 15 characters). Optional.
        path2: Second URL path text (max 15 characters). Optional.
        status: Ad status. One of: ENABLED, PAUSED. Default: ENABLED.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the created ad resource name.
    """
    if len(headlines) < 3:
        raise ValueError("At least 3 headlines are required.")
    if len(headlines) > 15:
        raise ValueError("Maximum 15 headlines allowed.")
    if len(descriptions) < 2:
        raise ValueError("At least 2 descriptions are required.")
    if len(descriptions) > 4:
        raise ValueError("Maximum 4 descriptions allowed.")

    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_service = client.get_service("AdGroupService")

    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_operation.create
    ad_group_ad.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )

    # Set status
    status_enum = client.enums.AdGroupAdStatusEnum
    ad_group_ad.status = getattr(status_enum, status)

    # Set up responsive search ad
    ad = ad_group_ad.ad
    ad.final_urls.append(final_url)

    for headline_text in headlines:
        ad_text_asset = client.get_type("AdTextAsset")
        ad_text_asset.text = headline_text
        ad.responsive_search_ad.headlines.append(ad_text_asset)

    for description_text in descriptions:
        ad_text_asset = client.get_type("AdTextAsset")
        ad_text_asset.text = description_text
        ad.responsive_search_ad.descriptions.append(ad_text_asset)

    if path1:
        ad.responsive_search_ad.path1 = path1
    if path2:
        ad.responsive_search_ad.path2 = path2

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_operation]
    )

    return {
        "ad_resource_name": response.results[0].resource_name,
        "message": f"Responsive search ad created successfully in ad group {ad_group_id}.",
    }


@mcp.tool()
def add_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: List[Dict[str, str]],
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds keywords to an ad group.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group to add keywords to.
        keywords: List of keyword objects, each with:
            - text: The keyword text (e.g., "buy shoes online").
            - match_type: One of: EXACT, PHRASE, BROAD. Default: BROAD.
            - cpc_bid_micros: Optional CPC bid in micros for this keyword.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with created keyword resource names and count.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ad_group_criterion_service = client.get_service("AdGroupCriterionService")
    ad_group_service = client.get_service("AdGroupService")

    operations = []
    for kw in keywords:
        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.create
        criterion.ad_group = ad_group_service.ad_group_path(
            customer_id, ad_group_id
        )
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED

        # Set keyword
        criterion.keyword.text = kw["text"]
        match_type = kw.get("match_type", "BROAD")
        match_type_enum = client.enums.KeywordMatchTypeEnum
        criterion.keyword.match_type = getattr(match_type_enum, match_type)

        # Set optional bid
        if "cpc_bid_micros" in kw:
            criterion.cpc_bid_micros = int(kw["cpc_bid_micros"])

        operations.append(operation)

    response = ad_group_criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=operations
    )

    return {
        "keyword_resource_names": [
            result.resource_name for result in response.results
        ],
        "keywords_added": len(response.results),
        "message": f"{len(response.results)} keyword(s) added to ad group {ad_group_id}.",
    }


@mcp.tool()
def update_ad_status(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    status: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, str]:
    """Enables, pauses, or removes an ad.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group containing the ad.
        ad_id: The ID of the ad to update.
        status: New status. One of: ENABLED, PAUSED, REMOVED.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the updated resource name and confirmation message.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ad_group_ad_service = client.get_service("AdGroupAdService")
    ad_group_ad_operation = client.get_type("AdGroupAdOperation")
    ad_group_ad = ad_group_ad_operation.update
    ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(
        customer_id, ad_group_id, ad_id
    )

    status_enum = client.enums.AdGroupAdStatusEnum
    ad_group_ad.status = getattr(status_enum, status)

    client.copy_from(
        ad_group_ad_operation.update_mask,
        utils.create_field_mask(ad_group_ad),
    )

    response = ad_group_ad_service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[ad_group_ad_operation]
    )

    return {
        "ad_resource_name": response.results[0].resource_name,
        "message": f"Ad {ad_id} status set to {status}.",
    }


@mcp.tool()
def update_keyword(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    status: Optional[str] = None,
    cpc_bid_micros: Optional[int] = None,
    login_customer_id: Optional[str] = None,
) -> Dict[str, str]:
    """Updates a keyword's status or bid.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group containing the keyword.
        criterion_id: The criterion ID of the keyword.
        status: New status. One of: ENABLED, PAUSED, REMOVED. Optional.
        cpc_bid_micros: New CPC bid in micros. Optional.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the updated resource name and confirmation message.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    criterion_service = client.get_service("AdGroupCriterionService")
    operation = client.get_type("AdGroupCriterionOperation")
    criterion = operation.update
    criterion.resource_name = criterion_service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )

    if status is not None:
        status_enum = client.enums.AdGroupCriterionStatusEnum
        criterion.status = getattr(status_enum, status)
    if cpc_bid_micros is not None:
        criterion.cpc_bid_micros = cpc_bid_micros

    client.copy_from(
        operation.update_mask,
        utils.create_field_mask(criterion),
    )

    response = criterion_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "keyword_resource_name": response.results[0].resource_name,
        "message": f"Keyword {criterion_id} updated successfully.",
    }


@mcp.tool()
async def remove_ad(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    login_customer_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, str]:
    """Permanently removes an ad from an ad group.

    Use this to delete disapproved, old, or unwanted ads. This action
    cannot be undone — the ad will be permanently removed.
    Requires user confirmation via interactive elicitation before proceeding.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group containing the ad.
        ad_id: The ID of the ad to remove.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with confirmation message.
    """
    from pydantic import BaseModel, Field

    class Confirmation(BaseModel):
        confirm: bool = Field(
            description="Set to true to permanently remove this ad."
        )

    # Ask user for confirmation via elicitation
    # Falls back gracefully if client doesn't support elicitation
    try:
        result = await ctx.elicit(
            message=(
                f"⚠️ DESTRUCTIVE ACTION: Permanently remove "
                f"ad {ad_id} from ad group {ad_group_id} "
                f"in account {customer_id}? "
                f"This cannot be undone."
            ),
            schema=Confirmation,
        )
        if result.action != "accept" or not result.data.confirm:
            return {"message": "Ad removal cancelled by user."}
    except Exception:
        # Client doesn't support elicitation yet, proceed
        pass

    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = client.get_service("AdGroupAdService")

    resource_name = service.ad_group_ad_path(customer_id, ad_group_id, ad_id)
    operation = client.get_type("AdGroupAdOperation")
    operation.remove = resource_name

    response = service.mutate_ad_group_ads(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "removed_resource_name": response.results[0].resource_name,
        "message": (
            f"Ad {ad_id} permanently removed " f"from ad group {ad_group_id}."
        ),
    }


@mcp.tool()
async def remove_keyword(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    login_customer_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, str]:
    """Permanently removes a keyword from an ad group.

    This action cannot be undone.
    Requires user confirmation via interactive elicitation before proceeding.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group containing the keyword.
        criterion_id: The criterion ID of the keyword to remove.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with confirmation message.
    """
    from pydantic import BaseModel, Field

    class Confirmation(BaseModel):
        confirm: bool = Field(
            description="Set to true to permanently remove this keyword."
        )

    # Ask user for confirmation via elicitation
    # Auto-works when client supports elicitation/create method
    try:
        result = await ctx.elicit(
            message=(
                f"⚠️ DESTRUCTIVE ACTION: Permanently remove "
                f"keyword {criterion_id} from ad group "
                f"{ad_group_id} in account {customer_id}? "
                f"This cannot be undone."
            ),
            schema=Confirmation,
        )
        if result.action != "accept" or not result.data.confirm:
            return {"message": "Keyword removal cancelled by user."}
    except Exception:
        # Client doesn't support elicitation yet
        pass

    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = client.get_service("AdGroupCriterionService")

    resource_name = service.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    operation = client.get_type("AdGroupCriterionOperation")
    operation.remove = resource_name

    response = service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "removed_resource_name": response.results[0].resource_name,
        "message": (
            f"Keyword {criterion_id} permanently removed "
            f"from ad group {ad_group_id}."
        ),
    }


@mcp.tool()
def add_negative_keywords(
    customer_id: str,
    campaign_id: str,
    keywords: List[Dict[str, str]],
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds negative keywords to a campaign to block irrelevant traffic.

    Negative keywords prevent your ads from showing for specific search terms.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign to add negative keywords to.
        keywords: List of keyword objects, each with:
            - text: The keyword text (e.g., "free LMS").
            - match_type: One of: EXACT, PHRASE, BROAD. Default: BROAD.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with created negative keyword resource names.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")

    operations = []
    for kw in keywords:
        operation = client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(
            customer_id, campaign_id
        )
        criterion.negative = True
        criterion.keyword.text = kw["text"]
        match_type = kw.get("match_type", "BROAD")
        match_enum = client.enums.KeywordMatchTypeEnum
        criterion.keyword.match_type = getattr(match_enum, match_type)
        operations.append(operation)

    response = service.mutate_campaign_criteria(
        customer_id=customer_id, operations=operations
    )

    return {
        "negative_keyword_resource_names": [
            r.resource_name for r in response.results
        ],
        "keywords_added": len(response.results),
        "message": (
            f"{len(response.results)} negative keyword(s) "
            f"added to campaign {campaign_id}."
        ),
    }


@mcp.tool()
def set_geo_targets(
    customer_id: str,
    campaign_id: str,
    location_ids: List[int],
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Sets geo targeting for a campaign by adding location criteria.

    Common location IDs (Google Ads geo target constants):
        US=2840, UK=2826, Canada=2124, Australia=2036,
        India=2356, Singapore=2702, UAE=2784,
        Germany=2276, France=2250

    Find more IDs at:
    https://developers.google.com/google-ads/api/data/geotargets

    Args:
        customer_id: The Google Ads customer ID.
        campaign_id: The ID of the campaign.
        location_ids: List of geo target constant IDs.
        login_customer_id: Optional manager account ID.

    Returns:
        Dictionary with created location criteria.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")

    operations = []
    for loc_id in location_ids:
        operation = client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(
            customer_id, campaign_id
        )
        criterion.location.geo_target_constant = f"geoTargetConstants/{loc_id}"
        operations.append(operation)

    response = service.mutate_campaign_criteria(
        customer_id=customer_id, operations=operations
    )

    return {
        "location_resource_names": [r.resource_name for r in response.results],
        "locations_added": len(response.results),
        "message": (
            f"{len(response.results)} geo target(s) "
            f"added to campaign {campaign_id}."
        ),
    }


@mcp.tool()
def set_ad_schedule(
    customer_id: str,
    campaign_id: str,
    schedules: List[Dict[str, Any]],
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Sets ad schedule (day/hour targeting) for a campaign.

    Controls which days and hours ads are shown.

    Args:
        customer_id: The Google Ads customer ID.
        campaign_id: The ID of the campaign.
        schedules: List of schedule objects, each with:
            - day_of_week: One of MONDAY, TUESDAY, WEDNESDAY,
                THURSDAY, FRIDAY, SATURDAY, SUNDAY.
            - start_hour: Start hour (0-23).
            - start_minute: One of ZERO, FIFTEEN, THIRTY,
                FORTY_FIVE. Default: ZERO.
            - end_hour: End hour (0-23). Use 24 for midnight.
            - end_minute: One of ZERO, FIFTEEN, THIRTY,
                FORTY_FIVE. Default: ZERO.
        login_customer_id: Optional manager account ID.

    Returns:
        Dictionary with created schedule criteria.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = client.get_service("CampaignCriterionService")
    campaign_service = client.get_service("CampaignService")

    operations = []
    for sched in schedules:
        operation = client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(
            customer_id, campaign_id
        )
        day_enum = client.enums.DayOfWeekEnum
        criterion.ad_schedule.day_of_week = getattr(
            day_enum, sched["day_of_week"]
        )
        criterion.ad_schedule.start_hour = sched["start_hour"]
        criterion.ad_schedule.end_hour = sched["end_hour"]

        minute_enum = client.enums.MinuteOfHourEnum
        start_min = sched.get("start_minute", "ZERO")
        end_min = sched.get("end_minute", "ZERO")
        criterion.ad_schedule.start_minute = getattr(minute_enum, start_min)
        criterion.ad_schedule.end_minute = getattr(minute_enum, end_min)
        operations.append(operation)

    response = service.mutate_campaign_criteria(
        customer_id=customer_id, operations=operations
    )

    return {
        "schedule_resource_names": [r.resource_name for r in response.results],
        "schedules_added": len(response.results),
        "message": (
            f"{len(response.results)} ad schedule(s) "
            f"added to campaign {campaign_id}."
        ),
    }
