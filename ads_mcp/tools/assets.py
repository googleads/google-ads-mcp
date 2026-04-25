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

"""Assets + asset-link tools.

Assets are the reusable building blocks of extensions (sitelinks, callouts,
structured snippets, calls, images) and Performance Max creatives. The flow is:

  1. Create the asset (e.g. a Sitelink with link_text + final_urls).
  2. Link it at the right scope: Customer (account-wide), Campaign, or AdGroup.
  3. The field_type on the link determines how the asset is used (SITELINK,
     CALLOUT, STRUCTURED_SNIPPET, CALL, IMAGE, etc.).

An asset can be linked multiple places; unlinking removes it from that scope
but doesn't delete the underlying asset.
"""

import base64
from typing import Any
from urllib.request import Request, urlopen

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_assets(
    customer_id: str,
    type_filter: list[str] | None = None,
    name_contains: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Lists assets in the account.

    Args:
        customer_id: 10-digit customer id.
        type_filter: Optional list of asset types, e.g.
            ['SITELINK','CALLOUT','STRUCTURED_SNIPPET','CALL','IMAGE',
             'TEXT','PROMOTION','PRICE','LEAD_FORM','YOUTUBE_VIDEO',
             'BUSINESS_PROFILE_LOCATION','HOTEL_CALLOUT','MEDIA_BUNDLE'].
        name_contains: Optional substring filter on asset.name.
        limit: Max rows.
    """
    where = []
    if type_filter:
        where.append(f"asset.type IN ({_common.comma_join(type_filter)})")
    if name_contains:
        safe = name_contains.replace("'", "\\'")
        where.append(f"asset.name LIKE '%{safe}%'")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = (
        "SELECT asset.id, asset.name, asset.type, asset.resource_name, "
        "asset.sitelink_asset.link_text, asset.sitelink_asset.description1, "
        "asset.sitelink_asset.description2, asset.callout_asset.callout_text, "
        "asset.structured_snippet_asset.header, "
        "asset.structured_snippet_asset.values, "
        "asset.call_asset.phone_number, asset.call_asset.country_code, "
        "asset.image_asset.file_size "
        f"FROM asset{clause} LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_sitelink_asset(
    customer_id: str,
    link_text: str,
    final_urls: list[str],
    description1: str | None = None,
    description2: str | None = None,
    name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Sitelink asset.

    Sitelinks are the extra links that appear under a search ad (e.g. "Pricing",
    "Free Trial", "Demo"). Each needs link_text (<= 25 chars) and at least one
    final URL. Descriptions (<= 35 chars each) are optional but highly
    recommended — ads with both descriptions often get the enhanced 4-line
    sitelink layout.

    After creating, link the returned resource_name to a Campaign / AdGroup /
    Customer with `link_assets_to_campaign` / `_ad_group` / `_customer` and
    field_type='SITELINK'.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    a = op.create
    if name:
        a.name = name
    a.sitelink_asset.link_text = link_text
    a.sitelink_asset.final_urls.extend(final_urls)
    if description1:
        a.sitelink_asset.description1 = description1
    if description2:
        a.sitelink_asset.description2 = description2

    with _common.google_ads_errors():
        response = service.mutate_assets(
            request=_common.build_request(
                client, "MutateAssetsRequest",
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
def create_callout_asset(
    customer_id: str,
    text: str,
    name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Callout asset (short plain-text brag: "Free Shipping", "24/7 Support"). Max 25 chars."""
    client = utils.get_googleads_client()
    service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    a = op.create
    if name:
        a.name = name
    a.callout_asset.callout_text = text

    with _common.google_ads_errors():
        response = service.mutate_assets(
            request=_common.build_request(
                client, "MutateAssetsRequest",
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
def create_structured_snippet_asset(
    customer_id: str,
    header: str,
    values: list[str],
    name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Structured Snippet asset.

    Args:
        header: One of Google's predefined headers ('Services', 'Courses',
            'Destinations', 'Featured hotels', 'Insurance coverage', 'Models',
            'Neighborhoods', 'Shows', 'Styles', 'Types', 'Amenities',
            'Brands', 'Degree programs', 'Show types').
        values: 3-10 values under that header (each <= 25 chars).
    """
    client = utils.get_googleads_client()
    service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    a = op.create
    if name:
        a.name = name
    a.structured_snippet_asset.header = header
    a.structured_snippet_asset.values.extend(values)

    with _common.google_ads_errors():
        response = service.mutate_assets(
            request=_common.build_request(
                client, "MutateAssetsRequest",
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
def create_call_asset(
    customer_id: str,
    phone_number: str,
    country_code: str,
    call_conversion_action_id: str | None = None,
    name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Call asset (click-to-call phone number).

    Args:
        phone_number: E.g. '+14155551234' or '415-555-1234'.
        country_code: 2-letter ISO country (e.g. 'US', 'IN').
        call_conversion_action_id: Optional conversion action to credit calls to.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    a = op.create
    if name:
        a.name = name
    a.call_asset.country_code = country_code
    a.call_asset.phone_number = phone_number
    if call_conversion_action_id:
        a.call_asset.call_conversion_reporting_state = (
            client.enums.CallConversionReportingStateEnum.USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION
        )
        a.call_asset.call_conversion_action = _common.conversion_action_path(
            customer_id, call_conversion_action_id
        )

    with _common.google_ads_errors():
        response = service.mutate_assets(
            request=_common.build_request(
                client, "MutateAssetsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


def _fetch_image_bytes(url: str) -> bytes:
    """Download an image from a URL. Kept private; used by create_image_asset."""
    req = Request(url, headers={"User-Agent": "google-ads-mcp/image-asset"})
    with urlopen(req, timeout=30) as resp:  # nosec B310 - url is user-supplied by design
        return resp.read()


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_image_asset(
    customer_id: str,
    name: str,
    image_url: str | None = None,
    image_base64: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates an Image asset (for image extensions, Display ads, Performance Max, etc.).

    Provide exactly one of `image_url` (we download it) or `image_base64`.
    Images must be JPG/PNG/GIF, max 5MB. For Performance Max you typically want
    both landscape (1200x628) and square (1200x1200).

    The created asset's resource_name can then be linked to a campaign with
    `link_assets_to_campaign(..., field_type='LANDSCAPE_IMAGE' or 'SQUARE_IMAGE')`
    or embedded in a Performance Max asset group.
    """
    if not (image_url or image_base64):
        raise ValueError(
            "Pass either image_url (we'll fetch it) or image_base64."
        )
    if image_url and image_base64:
        raise ValueError(
            "Pass only one of image_url or image_base64, not both."
        )

    data = _fetch_image_bytes(image_url) if image_url else base64.b64decode(
        image_base64
    )
    if len(data) > 5 * 1024 * 1024:
        raise ValueError(
            f"Image is {len(data)} bytes; Google caps image assets at 5MB."
        )

    client = utils.get_googleads_client()
    service = client.get_service("AssetService")
    op = client.get_type("AssetOperation")
    a = op.create
    a.name = name
    # asset.type is output-only — the API infers it from the populated
    # asset-data oneof (`image_asset` here).
    a.image_asset.data = data

    with _common.google_ads_errors():
        response = service.mutate_assets(
            request=_common.build_request(
                client, "MutateAssetsRequest",
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
def link_assets_to_customer(
    customer_id: str,
    asset_resource_names: list[str],
    field_type: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Links assets account-wide (CustomerAssetService).

    Account-wide links are the 'catch-all' — they apply to every eligible
    campaign unless a campaign-level or ad-group-level link overrides them.

    Args:
        asset_resource_names: e.g. ['customers/.../assets/123'].
        field_type: How the asset is used. Common values: 'SITELINK', 'CALLOUT',
            'STRUCTURED_SNIPPET', 'CALL', 'IMAGE', 'PROMOTION', 'PRICE',
            'LEAD_FORM'.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CustomerAssetService")
    ops = []
    for rn in asset_resource_names:
        op = client.get_type("CustomerAssetOperation")
        op.create.asset = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum[field_type]
        ops.append(op)
    with _common.google_ads_errors():
        response = service.mutate_customer_assets(
            request=_common.build_request(
                client, "MutateCustomerAssetsRequest",
                customer_id=customer_id,
                operations=ops,
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
def link_assets_to_campaign(
    customer_id: str,
    campaign_id: str,
    asset_resource_names: list[str],
    field_type: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Links assets to a specific campaign (CampaignAssetService).

    Campaign-level links override account-level links. Use this when only
    certain campaigns should get a sitelink/callout/etc.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignAssetService")
    ops = []
    for rn in asset_resource_names:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign = _common.campaign_path(customer_id, campaign_id)
        op.create.asset = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum[field_type]
        ops.append(op)
    with _common.google_ads_errors():
        response = service.mutate_campaign_assets(
            request=_common.build_request(
                client, "MutateCampaignAssetsRequest",
                customer_id=customer_id,
                operations=ops,
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
def link_assets_to_ad_group(
    customer_id: str,
    ad_group_id: str,
    asset_resource_names: list[str],
    field_type: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Links assets to a specific ad group (AdGroupAssetService).

    AdGroup-level is the narrowest scope and overrides both campaign and
    account links for matching field_type.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAssetService")
    ops = []
    for rn in asset_resource_names:
        op = client.get_type("AdGroupAssetOperation")
        op.create.ad_group = _common.ad_group_path(customer_id, ad_group_id)
        op.create.asset = rn
        op.create.field_type = client.enums.AssetFieldTypeEnum[field_type]
        ops.append(op)
    with _common.google_ads_errors():
        response = service.mutate_ad_group_assets(
            request=_common.build_request(
                client, "MutateAdGroupAssetsRequest",
                customer_id=customer_id,
                operations=ops,
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def unlink_customer_asset(
    customer_id: str,
    customer_asset_resource_name: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes an account-level asset link (does not delete the asset)."""
    client = utils.get_googleads_client()
    service = client.get_service("CustomerAssetService")
    op = client.get_type("CustomerAssetOperation")
    op.remove = customer_asset_resource_name
    with _common.google_ads_errors():
        response = service.mutate_customer_assets(
            request=_common.build_request(
                client, "MutateCustomerAssetsRequest",
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
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def unlink_campaign_asset(
    customer_id: str,
    campaign_asset_resource_name: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes a campaign-level asset link (does not delete the asset)."""
    client = utils.get_googleads_client()
    service = client.get_service("CampaignAssetService")
    op = client.get_type("CampaignAssetOperation")
    op.remove = campaign_asset_resource_name
    with _common.google_ads_errors():
        response = service.mutate_campaign_assets(
            request=_common.build_request(
                client, "MutateCampaignAssetsRequest",
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
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def unlink_ad_group_asset(
    customer_id: str,
    ad_group_asset_resource_name: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes an ad-group-level asset link (does not delete the asset)."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAssetService")
    op = client.get_type("AdGroupAssetOperation")
    op.remove = ad_group_asset_resource_name
    with _common.google_ads_errors():
        response = service.mutate_ad_group_assets(
            request=_common.build_request(
                client, "MutateAdGroupAssetsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
