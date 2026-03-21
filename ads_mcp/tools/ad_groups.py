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

"""Tools for creating and managing ad groups via the MCP server."""

from typing import Dict, Any, Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    cpc_bid_micros: int = 1000000,
    ad_group_type: str = "SEARCH_STANDARD",
    status: str = "ENABLED",
) -> Dict[str, Any]:
    """Creates a new ad group within a campaign.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign to add the ad group to.
        name: The name for the new ad group.
        cpc_bid_micros: Default max CPC bid in micros (e.g., 1000000 = $1.00). Default: 1000000.
        ad_group_type: Ad group type. One of: SEARCH_STANDARD, DISPLAY_STANDARD, SHOPPING_PRODUCT_ADS, VIDEO_BUMPER, VIDEO_TRUE_VIEW_IN_STREAM. Default: SEARCH_STANDARD.
        status: Initial status. One of: ENABLED, PAUSED. Default: ENABLED.

    Returns:
        Dictionary with the created ad group resource name.
    """
    client = utils.get_googleads_client()
    ad_group_service = client.get_service("AdGroupService")
    campaign_service = client.get_service("CampaignService")

    ad_group_operation = client.get_type("AdGroupOperation")
    ad_group = ad_group_operation.create
    ad_group.name = name
    ad_group.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    ad_group.cpc_bid_micros = cpc_bid_micros

    # Set ad group type
    type_enum = client.enums.AdGroupTypeEnum
    ad_group.type_ = getattr(type_enum, ad_group_type)

    # Set status
    status_enum = client.enums.AdGroupStatusEnum
    ad_group.status = getattr(status_enum, status)

    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_operation]
    )

    return {
        "ad_group_resource_name": response.results[0].resource_name,
        "message": f"Ad group '{name}' created successfully in campaign {campaign_id}.",
    }


@mcp.tool()
def update_ad_group(
    customer_id: str,
    ad_group_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    cpc_bid_micros: Optional[int] = None,
) -> Dict[str, Any]:
    """Updates an existing ad group's settings.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group to update.
        name: New ad group name. Optional.
        status: New status. One of: ENABLED, PAUSED, REMOVED. Optional.
        cpc_bid_micros: New default max CPC bid in micros. Optional.

    Returns:
        Dictionary with the updated resource name and confirmation message.
    """
    client = utils.get_googleads_client()
    ad_group_service = client.get_service("AdGroupService")
    ad_group_operation = client.get_type("AdGroupOperation")
    ad_group = ad_group_operation.update
    ad_group.resource_name = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )

    if name is not None:
        ad_group.name = name
    if status is not None:
        status_enum = client.enums.AdGroupStatusEnum
        ad_group.status = getattr(status_enum, status)
    if cpc_bid_micros is not None:
        ad_group.cpc_bid_micros = cpc_bid_micros

    client.copy_from(
        ad_group_operation.update_mask,
        utils.create_field_mask(ad_group),
    )

    response = ad_group_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ad_group_operation]
    )

    return {
        "ad_group_resource_name": response.results[0].resource_name,
        "message": f"Ad group {ad_group_id} updated successfully.",
    }
