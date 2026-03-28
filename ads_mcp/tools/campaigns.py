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

"""Tools for creating, editing, and managing campaigns via the MCP server."""

from typing import Dict, Any, Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def create_campaign(
    customer_id: str,
    name: str,
    budget_amount_micros: int,
    advertising_channel_type: str = "SEARCH",
    status: str = "PAUSED",
    bidding_strategy_type: str = "MANUAL_CPC",
    target_cpa_micros: Optional[int] = None,
    target_roas: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new Google Ads campaign with a budget.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        name: The name for the new campaign.
        budget_amount_micros: Daily budget in micros (e.g., 10000000 = $10.00).
        advertising_channel_type: Channel type. One of: SEARCH, DISPLAY, SHOPPING, VIDEO, MULTI_CHANNEL. Default: SEARCH.
        status: Initial campaign status. One of: ENABLED, PAUSED. Default: PAUSED.
        bidding_strategy_type: Bidding strategy. One of: MANUAL_CPC, MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE, TARGET_CPA, TARGET_ROAS, TARGET_SPEND. Default: MANUAL_CPC.
        target_cpa_micros: Target CPA in micros, required when bidding_strategy_type is TARGET_CPA.
        target_roas: Target ROAS (e.g., 2.0 for 200%), required when bidding_strategy_type is TARGET_ROAS.
        start_date: Campaign start date in YYYY-MM-DD format. Optional.
        end_date: Campaign end date in YYYY-MM-DD format. Optional.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with created campaign and budget resource names.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    # Step 1: Create the campaign budget
    campaign_budget_service = client.get_service("CampaignBudgetService")
    campaign_budget_operation = client.get_type("CampaignBudgetOperation")
    campaign_budget = campaign_budget_operation.create
    campaign_budget.name = f"Budget for {name}"
    campaign_budget.amount_micros = budget_amount_micros
    campaign_budget.delivery_method = (
        client.enums.BudgetDeliveryMethodEnum.STANDARD
    )

    budget_response = campaign_budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[campaign_budget_operation]
    )
    budget_resource_name = budget_response.results[0].resource_name

    # Step 2: Create the campaign
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = name
    campaign.campaign_budget = budget_resource_name

    # Set advertising channel type
    channel_type_enum = client.enums.AdvertisingChannelTypeEnum
    campaign.advertising_channel_type = getattr(
        channel_type_enum, advertising_channel_type
    )

    # Set status
    status_enum = client.enums.CampaignStatusEnum
    campaign.status = getattr(status_enum, status)

    # Set bidding strategy using client.copy_from for empty message fields
    if bidding_strategy_type == "MANUAL_CPC":
        client.copy_from(campaign.manual_cpc, client.get_type("ManualCpc"))
    elif bidding_strategy_type == "MAXIMIZE_CONVERSIONS":
        client.copy_from(
            campaign.maximize_conversions,
            client.get_type("MaximizeConversions"),
        )
    elif bidding_strategy_type == "MAXIMIZE_CONVERSION_VALUE":
        client.copy_from(
            campaign.maximize_conversion_value,
            client.get_type("MaximizeConversionValue"),
        )
    elif bidding_strategy_type == "TARGET_CPA":
        if target_cpa_micros is None:
            raise ValueError(
                "target_cpa_micros is required for TARGET_CPA bidding."
            )
        campaign.maximize_conversions.target_cpa_micros = target_cpa_micros
    elif bidding_strategy_type == "TARGET_ROAS":
        if target_roas is None:
            raise ValueError("target_roas is required for TARGET_ROAS bidding.")
        campaign.maximize_conversion_value.target_roas = target_roas
    elif bidding_strategy_type == "TARGET_SPEND":
        client.copy_from(campaign.target_spend, client.get_type("TargetSpend"))

    # Set network settings for Search campaigns
    if advertising_channel_type == "SEARCH":
        campaign.network_settings.target_google_search = True
        campaign.network_settings.target_search_network = True

    # Set EU political advertising compliance field (required since API v19.2)
    # This is an enum, not a bool.
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    # Set dates if provided
    if start_date:
        campaign.start_date = start_date
    if end_date:
        campaign.end_date = end_date

    campaign_response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_operation]
    )
    campaign_resource_name = campaign_response.results[0].resource_name

    return {
        "campaign_resource_name": campaign_resource_name,
        "budget_resource_name": budget_resource_name,
        "message": f"Campaign '{name}' created successfully.",
    }


@mcp.tool()
def create_performance_max_campaign(
    customer_id: str,
    name: str,
    budget_amount_micros: int,
    business_name_asset_resource_name: str,
    logo_asset_resource_name: str,
    status: str = "PAUSED",
    bidding_strategy_type: str = "MAXIMIZE_CONVERSIONS",
    target_cpa_micros: Optional[int] = None,
    target_roas: Optional[float] = None,
    final_url_expansion_opt_out: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a Performance Max campaign with a budget, business name, and logo.

    PMax campaigns require a business name and logo asset linked at the campaign
    level (Brand Guidelines). Create these assets first using create_text_asset
    (for business name) and create_image_asset (for logo), then pass their
    resource names here.

    After creating the campaign, create more assets and an asset group using
    create_text_asset, create_image_asset, create_youtube_video_asset,
    and then create_asset_group.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        name: The name for the new campaign.
        budget_amount_micros: Daily budget in micros (e.g., 10000000 = $10.00).
        business_name_asset_resource_name: Resource name of a text asset for the business name.
        logo_asset_resource_name: Resource name of an image asset for the logo (square, 1200x1200).
        status: Initial campaign status. One of: ENABLED, PAUSED. Default: PAUSED.
        bidding_strategy_type: One of: MAXIMIZE_CONVERSIONS, MAXIMIZE_CONVERSION_VALUE.
            Default: MAXIMIZE_CONVERSIONS.
        target_cpa_micros: Target CPA in micros, optional with MAXIMIZE_CONVERSIONS.
        target_roas: Target ROAS (e.g., 2.0 for 200%), optional with MAXIMIZE_CONVERSION_VALUE.
        final_url_expansion_opt_out: Set True to opt out of final URL expansion. Default: False.
        start_date: Campaign start date in YYYY-MM-DD format. Optional.
        end_date: Campaign end date in YYYY-MM-DD format. Optional.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with created campaign and budget resource names.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ga_service = client.get_service("GoogleAdsService")

    operations = []

    # Operation 1: Create the campaign budget
    budget_op = client.get_type("MutateOperation")
    campaign_budget = budget_op.campaign_budget_operation.create
    campaign_budget.name = f"PMax Budget for {name}"
    campaign_budget.amount_micros = budget_amount_micros
    campaign_budget.delivery_method = (
        client.enums.BudgetDeliveryMethodEnum.STANDARD
    )
    campaign_budget.explicitly_shared = False
    # Use temporary resource name for referencing in same batch
    budget_temp_rn = f"customers/{customer_id}/campaignBudgets/-1"
    campaign_budget.resource_name = budget_temp_rn
    operations.append(budget_op)

    # Operation 2: Create the Performance Max campaign
    campaign_op = client.get_type("MutateOperation")
    campaign = campaign_op.campaign_operation.create
    campaign.name = name
    campaign.campaign_budget = budget_temp_rn

    # Performance Max specific settings
    campaign.advertising_channel_type = (
        client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    )

    # Set status
    status_enum = client.enums.CampaignStatusEnum
    campaign.status = getattr(status_enum, status)

    # Set bidding strategy
    if bidding_strategy_type == "MAXIMIZE_CONVERSIONS":
        if target_cpa_micros:
            campaign.maximize_conversions.target_cpa_micros = target_cpa_micros
        else:
            client.copy_from(
                campaign.maximize_conversions,
                client.get_type("MaximizeConversions"),
            )
    elif bidding_strategy_type == "MAXIMIZE_CONVERSION_VALUE":
        if target_roas:
            campaign.maximize_conversion_value.target_roas = target_roas
        else:
            client.copy_from(
                campaign.maximize_conversion_value,
                client.get_type("MaximizeConversionValue"),
            )

    # URL expansion
    if final_url_expansion_opt_out:
        campaign.url_expansion_opt_out = True

    # EU political advertising compliance
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    # Set dates if provided
    if start_date:
        campaign.start_date = start_date
    if end_date:
        campaign.end_date = end_date

    # Use temporary resource name for referencing in same batch
    campaign_temp_rn = f"customers/{customer_id}/campaigns/-2"
    campaign.resource_name = campaign_temp_rn
    operations.append(campaign_op)

    # Operation 3: Link business name asset to campaign
    biz_name_op = client.get_type("MutateOperation")
    biz_name_asset = biz_name_op.campaign_asset_operation.create
    biz_name_asset.campaign = campaign_temp_rn
    biz_name_asset.asset = business_name_asset_resource_name
    biz_name_asset.field_type = client.enums.AssetFieldTypeEnum.BUSINESS_NAME
    operations.append(biz_name_op)

    # Operation 4: Link logo asset to campaign
    logo_op = client.get_type("MutateOperation")
    logo_asset = logo_op.campaign_asset_operation.create
    logo_asset.campaign = campaign_temp_rn
    logo_asset.asset = logo_asset_resource_name
    logo_asset.field_type = client.enums.AssetFieldTypeEnum.LOGO
    operations.append(logo_op)

    # Execute batch mutate
    response = ga_service.mutate(
        customer_id=customer_id, mutate_operations=operations
    )

    budget_rn = response.mutate_operation_responses[
        0
    ].campaign_budget_result.resource_name
    campaign_rn = response.mutate_operation_responses[
        1
    ].campaign_result.resource_name

    return {
        "campaign_resource_name": campaign_rn,
        "budget_resource_name": budget_rn,
        "message": f"Performance Max campaign '{name}' created with business name and logo.",
    }


@mcp.tool()
def update_campaign(
    customer_id: str,
    campaign_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    budget_amount_micros: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates an existing Google Ads campaign's settings.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign to update.
        name: New campaign name. Optional.
        status: New status. One of: ENABLED, PAUSED, REMOVED. Optional.
        budget_amount_micros: New daily budget in micros (e.g., 10000000 = $10.00). Optional.
        start_date: New start date in YYYY-MM-DD format. Optional.
        end_date: New end date in YYYY-MM-DD format. Optional.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the updated resource names and a confirmation message.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    results = {}

    # Update campaign budget if specified
    if budget_amount_micros is not None:
        # First, get the current campaign's budget resource name
        ga_service = client.get_service("GoogleAdsService")
        query = (
            f"SELECT campaign.campaign_budget FROM campaign "
            f"WHERE campaign.id = {campaign_id}"
        )
        response = ga_service.search(customer_id=customer_id, query=query)
        budget_resource_name = None
        for row in response:
            budget_resource_name = row.campaign.campaign_budget
            break

        if budget_resource_name:
            budget_service = client.get_service("CampaignBudgetService")
            budget_operation = client.get_type("CampaignBudgetOperation")
            budget = budget_operation.update
            budget.resource_name = budget_resource_name
            budget.amount_micros = budget_amount_micros
            client.copy_from(
                budget_operation.update_mask,
                utils.create_field_mask(budget),
            )
            budget_response = budget_service.mutate_campaign_budgets(
                customer_id=customer_id, operations=[budget_operation]
            )
            results["budget_resource_name"] = budget_response.results[
                0
            ].resource_name

    # Update campaign fields if any are specified
    if any([name, status, start_date, end_date]):
        campaign_service = client.get_service("CampaignService")
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.update
        campaign.resource_name = campaign_service.campaign_path(
            customer_id, campaign_id
        )

        if name is not None:
            campaign.name = name
        if status is not None:
            status_enum = client.enums.CampaignStatusEnum
            campaign.status = getattr(status_enum, status)
        if start_date is not None:
            campaign.start_date = start_date
        if end_date is not None:
            campaign.end_date = end_date

        client.copy_from(
            campaign_operation.update_mask,
            utils.create_field_mask(campaign),
        )
        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        results["campaign_resource_name"] = campaign_response.results[
            0
        ].resource_name

    results["message"] = f"Campaign {campaign_id} updated successfully."
    return results


@mcp.tool()
def set_campaign_status(
    customer_id: str,
    campaign_id: str,
    status: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, str]:
    """Enables, pauses, or removes a Google Ads campaign.

    This is a convenience tool for quickly changing campaign status.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign.
        status: The new status. One of: ENABLED, PAUSED, REMOVED.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the updated resource name and confirmation message.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = campaign_service.campaign_path(
        customer_id, campaign_id
    )

    status_enum = client.enums.CampaignStatusEnum
    campaign.status = getattr(status_enum, status)

    client.copy_from(
        campaign_operation.update_mask,
        utils.create_field_mask(campaign),
    )

    response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_operation]
    )

    return {
        "campaign_resource_name": response.results[0].resource_name,
        "message": f"Campaign {campaign_id} status set to {status}.",
    }
