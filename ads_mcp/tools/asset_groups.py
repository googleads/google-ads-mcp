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

"""Tools for creating and managing Performance Max asset groups via the MCP server.

Performance Max campaigns require asset groups with minimum assets, and these
must be created together in a single batch mutate request. This module handles
that complexity.
"""

from typing import Dict, Any, List, Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def create_asset_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    final_url: str,
    headline_asset_resource_names: List[str],
    description_asset_resource_names: List[str],
    long_headline_asset_resource_names: List[str],
    marketing_image_asset_resource_names: List[str],
    square_marketing_image_asset_resource_names: List[str],
    logo_asset_resource_names: Optional[List[str]] = None,
    youtube_video_asset_resource_names: Optional[List[str]] = None,
    final_mobile_url: Optional[str] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    status: str = "ENABLED",
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates an asset group for a Performance Max campaign and links all provided assets to it.

    Asset groups and their assets must be created together in a single batch request.
    Create all required assets first using create_text_asset, create_image_asset, etc.,
    then pass their resource names here.

    Minimum asset requirements for Performance Max:
    - At least 3 headlines (max 15)
    - At least 2 descriptions (max 5)
    - At least 1 long headline (max 5)
    - At least 1 marketing image (landscape, 1200x628 recommended)
    - At least 1 square marketing image (1200x1200 recommended)
    - At least 1 logo (1200x1200 recommended)
    - YouTube videos are optional but recommended

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        campaign_id: The ID of the Performance Max campaign.
        name: Name for the asset group.
        final_url: The landing page URL for the asset group.
        headline_asset_resource_names: List of text asset resource names for headlines (min 3).
        description_asset_resource_names: List of text asset resource names for descriptions (min 2).
        long_headline_asset_resource_names: List of text asset resource names for long headlines (min 1).
        marketing_image_asset_resource_names: List of image asset resource names for landscape images (min 1).
        square_marketing_image_asset_resource_names: List of image asset resource names for square images (min 1).
        logo_asset_resource_names: List of image asset resource names for logos (min 1).
        youtube_video_asset_resource_names: List of YouTube video asset resource names. Optional.
        final_mobile_url: Mobile landing page URL. Optional.
        path1: First URL path text (max 15 characters). Optional.
        path2: Second URL path text (max 15 characters). Optional.
        status: Asset group status. One of: ENABLED, PAUSED. Default: ENABLED.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the created asset group resource name and linked asset count.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ga_service = client.get_service("GoogleAdsService")
    campaign_service = client.get_service("CampaignService")

    operations = []

    # Operation 1: Create the asset group
    asset_group_op = client.get_type("MutateOperation")
    asset_group = asset_group_op.asset_group_operation.create
    asset_group.name = name
    asset_group.campaign = campaign_service.campaign_path(
        customer_id, campaign_id
    )
    asset_group.final_urls.append(final_url)
    if final_mobile_url:
        asset_group.final_mobile_urls.append(final_mobile_url)
    if path1:
        asset_group.path1 = path1
    if path2:
        asset_group.path2 = path2

    status_enum = client.enums.AssetGroupStatusEnum
    asset_group.status = getattr(status_enum, status)

    # Use a temporary resource name for the asset group so we can reference it
    # in subsequent operations within the same batch request
    asset_group_temp_rn = f"customers/{customer_id}/assetGroups/-1"
    asset_group.resource_name = asset_group_temp_rn

    operations.append(asset_group_op)

    # Helper to create AssetGroupAsset operations
    def _add_asset_group_asset_op(asset_rn, field_type_name):
        op = client.get_type("MutateOperation")
        aga = op.asset_group_asset_operation.create
        aga.asset_group = asset_group_temp_rn
        aga.asset = asset_rn
        field_type_enum = client.enums.AssetFieldTypeEnum
        aga.field_type = getattr(field_type_enum, field_type_name)
        operations.append(op)

    # Link headlines
    for rn in headline_asset_resource_names:
        _add_asset_group_asset_op(rn, "HEADLINE")

    # Link descriptions
    for rn in description_asset_resource_names:
        _add_asset_group_asset_op(rn, "DESCRIPTION")

    # Link long headlines
    for rn in long_headline_asset_resource_names:
        _add_asset_group_asset_op(rn, "LONG_HEADLINE")

    # Link marketing images (landscape)
    for rn in marketing_image_asset_resource_names:
        _add_asset_group_asset_op(rn, "MARKETING_IMAGE")

    # Link square marketing images
    for rn in square_marketing_image_asset_resource_names:
        _add_asset_group_asset_op(rn, "SQUARE_MARKETING_IMAGE")

    # Link logos (skip if Brand Guidelines is enabled — logos go at campaign level)
    if logo_asset_resource_names:
        for rn in logo_asset_resource_names:
            _add_asset_group_asset_op(rn, "LOGO")

    # Link YouTube videos if provided
    if youtube_video_asset_resource_names:
        for rn in youtube_video_asset_resource_names:
            _add_asset_group_asset_op(rn, "YOUTUBE_VIDEO")

    # Execute the batch mutate
    response = ga_service.mutate(
        customer_id=customer_id, mutate_operations=operations
    )

    # First result is the asset group, rest are asset links
    asset_group_result = response.mutate_operation_responses[0]
    asset_group_rn = asset_group_result.asset_group_result.resource_name

    return {
        "asset_group_resource_name": asset_group_rn,
        "assets_linked": len(operations) - 1,
        "message": f"Asset group '{name}' created with {len(operations) - 1} assets linked.",
    }


@mcp.tool()
def add_assets_to_asset_group(
    customer_id: str,
    asset_group_resource_name: str,
    assets: List[Dict[str, str]],
    login_customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Adds assets to an existing asset group.

    Use this to add more assets to an asset group after it's been created.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        asset_group_resource_name: The resource name of the asset group.
        assets: List of asset objects, each with:
            - asset_resource_name: The resource name of the asset.
            - field_type: One of: HEADLINE, DESCRIPTION, LONG_HEADLINE,
                MARKETING_IMAGE, SQUARE_MARKETING_IMAGE, LOGO,
                LANDSCAPE_LOGO, YOUTUBE_VIDEO, CALL_TO_ACTION_SELECTION.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with the count of assets added.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    ga_service = client.get_service("GoogleAdsService")

    operations = []
    for asset_info in assets:
        op = client.get_type("MutateOperation")
        aga = op.asset_group_asset_operation.create
        aga.asset_group = asset_group_resource_name
        aga.asset = asset_info["asset_resource_name"]

        field_type_enum = client.enums.AssetFieldTypeEnum
        aga.field_type = getattr(field_type_enum, asset_info["field_type"])

        operations.append(op)

    response = ga_service.mutate(
        customer_id=customer_id, mutate_operations=operations
    )

    return {
        "assets_added": len(response.mutate_operation_responses),
        "message": f"{len(response.mutate_operation_responses)} asset(s) added to asset group.",
    }


@mcp.tool()
def remove_asset_from_asset_group(
    customer_id: str,
    asset_group_resource_name: str,
    asset_resource_name: str,
    field_type: str,
    login_customer_id: Optional[str] = None,
) -> Dict[str, str]:
    """Removes an asset from an asset group.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        asset_group_resource_name: The resource name of the asset group.
        asset_resource_name: The resource name of the asset to remove.
        field_type: The field type of the asset. One of: HEADLINE, DESCRIPTION,
            LONG_HEADLINE, MARKETING_IMAGE, SQUARE_MARKETING_IMAGE, LOGO,
            LANDSCAPE_LOGO, YOUTUBE_VIDEO, CALL_TO_ACTION_SELECTION.
        login_customer_id: The Manager Account ID for accessing client accounts via a manager. Optional.

    Returns:
        Dictionary with confirmation message.
    """
    client = utils.get_googleads_client(login_customer_id=login_customer_id)
    asset_group_asset_service = client.get_service("AssetGroupAssetService")

    operation = client.get_type("AssetGroupAssetOperation")

    # Resource name format uses the field type string name
    asset_group_id = asset_group_resource_name.split("/")[-1]
    asset_id = asset_resource_name.split("/")[-1]
    resource_name = (
        f"customers/{customer_id}/assetGroupAssets/"
        f"{asset_group_id}~{asset_id}~{field_type}"
    )
    operation.remove = resource_name

    response = asset_group_asset_service.mutate_asset_group_assets(
        customer_id=customer_id, operations=[operation]
    )

    return {
        "removed_resource_name": response.results[0].resource_name,
        "message": "Asset removed from asset group.",
    }
