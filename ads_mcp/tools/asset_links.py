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

"""Tools for linking assets to campaigns and ad groups via the MCP server."""

from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import Context
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def link_asset_to_campaign(
    customer_id: str,
    campaign_id: str,
    asset_resource_name: str,
    field_type: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Links an existing asset to a campaign.

    After creating an asset (sitelink, callout, etc.), use this tool to
    attach it to a campaign so it appears with that campaign's ads.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign to link the asset to.
        asset_resource_name: The resource name of the asset (from create_*_asset tools).
        field_type: The asset field type. One of: SITELINK, CALLOUT, STRUCTURED_SNIPPET,
            CALL, PROMOTION, PRICE, LEAD_FORM, MOBILE_APP, HOTEL_CALLOUT, IMAGE,
            BUSINESS_NAME, BUSINESS_LOGO.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the created campaign asset link resource name.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    campaign_asset_service = client.get_service("CampaignAssetService")
    campaign_service = client.get_service("CampaignService")

    operation = client.get_type("CampaignAssetOperation")
    campaign_asset = operation.create
    campaign_asset.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    campaign_asset.asset = asset_resource_name

    field_type_enum = client.enums.AssetFieldTypeEnum
    campaign_asset.field_type = getattr(field_type_enum, field_type)

    response = campaign_asset_service.mutate_campaign_assets(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "campaign_asset_resource_name": response.results[0].resource_name,
        "message": f"Asset linked to campaign {campaign_id} as {field_type}.",
    }


@mcp.tool()
def link_asset_to_ad_group(
    customer_id: str,
    ad_group_id: str,
    asset_resource_name: str,
    field_type: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Links an existing asset to an ad group.

    After creating an asset (sitelink, callout, etc.), use this tool to
    attach it to an ad group so it appears with that ad group's ads.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        ad_group_id: The ID of the ad group to link the asset to.
        asset_resource_name: The resource name of the asset (from create_*_asset tools).
        field_type: The asset field type. One of: SITELINK, CALLOUT, STRUCTURED_SNIPPET,
            CALL, PROMOTION, PRICE, LEAD_FORM, MOBILE_APP, HOTEL_CALLOUT, IMAGE.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the created ad group asset link resource name.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ad_group_asset_service = client.get_service("AdGroupAssetService")
    ad_group_service = client.get_service("AdGroupService")

    operation = client.get_type("AdGroupAssetOperation")
    ad_group_asset = operation.create
    ad_group_asset.ad_group = ad_group_service.ad_group_path(
        customer_id, ad_group_id
    )
    ad_group_asset.asset = asset_resource_name

    field_type_enum = client.enums.AssetFieldTypeEnum
    ad_group_asset.field_type = getattr(field_type_enum, field_type)

    response = ad_group_asset_service.mutate_ad_group_assets(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "ad_group_asset_resource_name": response.results[0].resource_name,
        "message": f"Asset linked to ad group {ad_group_id} as {field_type}.",
    }


@mcp.tool()
def link_assets_to_customer(
    customer_id: str,
    asset_resource_names: List[str],
    field_type: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Links assets at the customer (account) level so they apply to all campaigns.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        asset_resource_names: List of asset resource names to link.
        field_type: The asset field type. One of: SITELINK, CALLOUT, STRUCTURED_SNIPPET,
            CALL, PROMOTION, PRICE, LEAD_FORM, MOBILE_APP, BUSINESS_NAME, BUSINESS_LOGO.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the created customer asset link resource names.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    customer_asset_service = client.get_service("CustomerAssetService")

    operations = []
    for asset_rn in asset_resource_names:
        operation = client.get_type("CustomerAssetOperation")
        customer_asset = operation.create
        customer_asset.asset = asset_rn

        field_type_enum = client.enums.AssetFieldTypeEnum
        customer_asset.field_type = getattr(field_type_enum, field_type)

        operations.append(operation)

    response = customer_asset_service.mutate_customer_assets(
        customer_id=customer_id, operations=operations
    )

    return {
        "customer_asset_resource_names": [
            result.resource_name for result in response.results
        ],
        "assets_linked": len(response.results),
        "message": f"{len(response.results)} asset(s) linked at account level as {field_type}.",
    }


@mcp.tool()
async def remove_campaign_asset(
    customer_id: str,
    campaign_id: str,
    asset_id: str,
    field_type: str,
    login_customer_id: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, str]:
    """Removes an asset link from a campaign.

    Requires user confirmation via interactive elicitation before proceeding.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the campaign.
        asset_id: The ID of the asset to unlink.
        field_type: The asset field type (e.g., SITELINK, CALLOUT).
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with confirmation message.
    """
    from pydantic import BaseModel, Field

    class Confirmation(BaseModel):
        confirm: bool = Field(description="Set to true to remove this asset.")

    try:
        result = await ctx.elicit(
            message=(
                f"⚠️ Remove {field_type} asset {asset_id} "
                f"from campaign {campaign_id}?"
            ),
            schema=Confirmation,
        )
        if result.action != "accept" or not result.data.confirm:
            return {"message": "Asset removal cancelled by user."}
    except Exception:
        pass

    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    campaign_asset_service = client.get_service("CampaignAssetService")

    resource_name = campaign_asset_service.campaign_asset_path(
        customer_id, campaign_id, asset_id, field_type
    )

    operation = client.get_type("CampaignAssetOperation")
    operation.remove = resource_name

    response = campaign_asset_service.mutate_campaign_assets(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "removed_resource_name": response.results[0].resource_name,
        "message": (
            f"Asset {asset_id} removed from " f"campaign {campaign_id}."
        ),
    }
