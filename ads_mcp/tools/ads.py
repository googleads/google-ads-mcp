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

"""Tools for managing AdGroupAd (ads) resources.

Note: Ad text fields on a Responsive Search Ad are immutable after creation.
To 'edit' an RSA you must remove + create. The lifecycle tools below let you
pause/enable/remove existing ads and create new ones.
"""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common

_BASE_FIELDS = (
    "ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.type, "
    "ad_group_ad.status, ad_group_ad.ad_group, ad_group_ad.ad.final_urls, "
    "ad_group_ad.ad.responsive_search_ad.headlines, "
    "ad_group_ad.ad.responsive_search_ad.descriptions, "
    "ad_group_ad.ad.responsive_search_ad.path1, "
    "ad_group_ad.ad.responsive_search_ad.path2, "
    "ad_group_ad.ad_strength, ad_group_ad.policy_summary.approval_status, "
    "ad_group_ad.resource_name"
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_ads(
    customer_id: str,
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
    status_filter: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Lists ads under an ad group, a campaign, or the whole account.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Optional scope.
        campaign_id: Optional scope.
        status_filter: e.g. ['ENABLED','PAUSED','REMOVED'].
        limit: Max rows.
    """
    where = []
    if ad_group_id:
        where.append(f"ad_group.id = {int(ad_group_id)}")
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    if status_filter:
        where.append(
            f"ad_group_ad.status IN ({_common.comma_join(status_filter)})"
        )
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = f"SELECT {_BASE_FIELDS} FROM ad_group_ad{clause} LIMIT {int(limit)}"
    return _common.gaql_search(customer_id, query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_ad(
    customer_id: str, ad_group_id: str, ad_id: str
) -> list[dict[str, Any]]:
    """Returns one ad by ad_group_id + ad_id."""
    query = (
        f"SELECT {_BASE_FIELDS} FROM ad_group_ad "
        f"WHERE ad_group.id = {int(ad_group_id)} "
        f"AND ad_group_ad.ad.id = {int(ad_id)} LIMIT 1"
    )
    return _common.gaql_search(customer_id, query)


def _set_status(
    customer_id: str,
    ad_group_id: str,
    ad_id: str,
    status: str,
    dry_run: bool,
) -> dict[str, Any]:
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    op.update.resource_name = _common.ad_group_ad_path(
        customer_id, ad_group_id, ad_id
    )
    op.update.status = client.enums.AdGroupAdStatusEnum[status]
    _common.set_field_mask(op, "status")
    with _common.google_ads_errors():
        response = service.mutate_ad_group_ads(
            request=_common.build_request(
                client, "MutateAdGroupAdsRequest",
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
def pause_ad(
    customer_id: str, ad_group_id: str, ad_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Pauses an ad."""
    return _set_status(customer_id, ad_group_id, ad_id, "PAUSED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True)
)
def enable_ad(
    customer_id: str, ad_group_id: str, ad_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Enables an ad."""
    return _set_status(customer_id, ad_group_id, ad_id, "ENABLED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def remove_ad(
    customer_id: str, ad_group_id: str, ad_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Removes an ad. Irreversible."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    op.remove = _common.ad_group_ad_path(customer_id, ad_group_id, ad_id)
    with _common.google_ads_errors():
        response = service.mutate_ad_group_ads(
            request=_common.build_request(
                client, "MutateAdGroupAdsRequest",
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
def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: str,
    final_urls: list[str],
    headlines: list[str],
    descriptions: list[str],
    path1: str | None = None,
    path2: str | None = None,
    status: str = "PAUSED",
    pinned_headlines: dict[int, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Responsive Search Ad in the given ad group.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Numeric ad group id.
        final_urls: Landing page URLs (at least one).
        headlines: 3-15 headline strings (each <= 30 chars).
        descriptions: 2-4 description strings (each <= 90 chars).
        path1: Optional display URL path part 1 (<= 15 chars).
        path2: Optional display URL path part 2 (<= 15 chars).
        status: 'PAUSED' (default) or 'ENABLED'.
        pinned_headlines: Optional {position: text} where position is 1, 2, or 3.
            Pins specific headlines to that slot.
        dry_run: If True, runs validate_only.
    """
    if len(headlines) < 3:
        raise ValueError("Need at least 3 headlines")
    if len(descriptions) < 2:
        raise ValueError("Need at least 2 descriptions")

    client = utils.get_googleads_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")

    aga = op.create
    aga.ad_group = _common.ad_group_path(customer_id, ad_group_id)
    aga.status = client.enums.AdGroupAdStatusEnum[status]
    aga.ad.final_urls.extend(final_urls)

    pinned = pinned_headlines or {}
    pin_lookup = {text: pos for pos, text in pinned.items()}
    for h in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = h
        if h in pin_lookup:
            asset.pinned_field = client.enums.ServedAssetFieldTypeEnum[
                f"HEADLINE_{pin_lookup[h]}"
            ]
        aga.ad.responsive_search_ad.headlines.append(asset)

    for d in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = d
        aga.ad.responsive_search_ad.descriptions.append(asset)

    if path1:
        aga.ad.responsive_search_ad.path1 = path1
    if path2:
        aga.ad.responsive_search_ad.path2 = path2

    with _common.google_ads_errors():
        response = service.mutate_ad_group_ads(
            request=_common.build_request(
                client, "MutateAdGroupAdsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
