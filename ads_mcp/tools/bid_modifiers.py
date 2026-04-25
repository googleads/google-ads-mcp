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

"""Ad-group bid modifiers (device, hotel).

WHY THIS EXISTS — modern Google Ads stores DEVICE bid modifiers at the
ad-group level only. The legacy stub row on `campaign_criterion` (where
`type=DEVICE`) always reports `bid_modifier=0.0` regardless of what the UI
shows, so a query like `SELECT campaign_criterion.bid_modifier FROM
campaign_criterion WHERE campaign_criterion.type = 'DEVICE'` cannot tell the
difference between "no modifier set" and "-100% (excluded)". And
`campaign_bid_modifier.device.type` is not a valid GAQL field at all.

The right resource is `ad_group_bid_modifier`. These tools wrap it.

bid_modifier values (per Google docs):
  -1.0  -> exclude this device entirely (UI shows '-100%')
  -0.5  -> -50%
   0.0  -> no adjustment (rarely set explicitly; equivalent to leaving unset)
   0.5  -> +50%
   1.0  -> +100% (i.e. double the bid)
"""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


_VALID_DEVICES = ("MOBILE", "TABLET", "DESKTOP", "CONNECTED_TV", "OTHER")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_ad_group_bid_modifiers(
    customer_id: str,
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Lists ad-group bid modifiers (device + hotel criterion types).

    For DEVICE modifiers, this is the *only* correct query — the
    `campaign_criterion` view returns legacy stub rows that always show
    `bid_modifier=0.0`.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Optional scope.
        campaign_id: Optional scope.
        limit: Max rows.
    """
    where = []
    if ad_group_id:
        where.append(f"ad_group.id = {int(ad_group_id)}")
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = (
        "SELECT ad_group_bid_modifier.resource_name, "
        "ad_group_bid_modifier.criterion_id, "
        "ad_group_bid_modifier.bid_modifier, "
        "ad_group_bid_modifier.device.type, "
        "ad_group.id, ad_group.name, campaign.id "
        f"FROM ad_group_bid_modifier{clause} LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_device_bid_modifiers(
    customer_id: str,
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Same as list_ad_group_bid_modifiers, filtered to DEVICE-only rows.

    Use this when you specifically want to see device-level adjustments
    (e.g. 'is Mobile excluded for ad group X?'). Each returned row has
    `ad_group_bid_modifier.device.type` ∈ {MOBILE, TABLET, DESKTOP,
    CONNECTED_TV, OTHER} and `ad_group_bid_modifier.bid_modifier` as a
    float (-1.0 means '-100% / exclude' in the UI).
    """
    where = ["ad_group_bid_modifier.device.type != 'UNSPECIFIED'"]
    if ad_group_id:
        where.append(f"ad_group.id = {int(ad_group_id)}")
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    clause = " WHERE " + " AND ".join(where)
    query = (
        "SELECT ad_group_bid_modifier.resource_name, "
        "ad_group_bid_modifier.criterion_id, "
        "ad_group_bid_modifier.bid_modifier, "
        "ad_group_bid_modifier.device.type, "
        "ad_group.id, ad_group.name, campaign.id "
        f"FROM ad_group_bid_modifier{clause} LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def add_ad_group_device_bid_modifier(
    customer_id: str,
    ad_group_id: str,
    device_type: str,
    bid_modifier: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds a device-level bid modifier to an ad group.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Numeric ad group id.
        device_type: One of 'MOBILE', 'TABLET', 'DESKTOP', 'CONNECTED_TV', 'OTHER'.
        bid_modifier: -1.0 to exclude (-100% in UI), or a multiplier offset.
            Examples:
              -1.0 -> exclude this device
              -0.5 -> -50%
               0.0 -> no change (rare to set explicitly)
               0.5 -> +50%
               1.0 -> +100% / double bid
        dry_run: If True, runs validate_only.

    Returns the resource_name, which embeds the criterion_id; pass that to
    `update_ad_group_bid_modifier` or `remove_ad_group_bid_modifier` later.
    """
    if device_type.upper() not in _VALID_DEVICES:
        raise ValueError(
            f"device_type must be one of {_VALID_DEVICES}, got {device_type!r}"
        )

    client = utils.get_googleads_client()
    service = client.get_service("AdGroupBidModifierService")
    op = client.get_type("AdGroupBidModifierOperation")
    bm = op.create
    bm.ad_group = _common.ad_group_path(customer_id, ad_group_id)
    bm.bid_modifier = float(bid_modifier)
    bm.device.type_ = client.enums.DeviceEnum[device_type.upper()]

    with _common.google_ads_errors():
        response = service.mutate_ad_group_bid_modifiers(
            request=_common.build_request(
                client, "MutateAdGroupBidModifiersRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "device_type": device_type.upper(),
        "bid_modifier": float(bid_modifier),
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def update_ad_group_bid_modifier(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    bid_modifier: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates the bid_modifier value on an existing ad-group bid modifier.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Numeric ad group id (left half of the ~-joined resource name).
        criterion_id: Numeric criterion id (right half).
        bid_modifier: New value (see add_ad_group_device_bid_modifier for ranges).
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupBidModifierService")
    op = client.get_type("AdGroupBidModifierOperation")
    op.update.resource_name = _common.ad_group_bid_modifier_path(
        customer_id, ad_group_id, criterion_id
    )
    op.update.bid_modifier = float(bid_modifier)
    _common.set_field_mask(op, "bid_modifier")

    with _common.google_ads_errors():
        response = service.mutate_ad_group_bid_modifiers(
            request=_common.build_request(
                client, "MutateAdGroupBidModifiersRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "bid_modifier": float(bid_modifier),
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def remove_ad_group_bid_modifier(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes an ad-group bid modifier (the device/hotel falls back to 'no adjustment')."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupBidModifierService")
    op = client.get_type("AdGroupBidModifierOperation")
    op.remove = _common.ad_group_bid_modifier_path(
        customer_id, ad_group_id, criterion_id
    )

    with _common.google_ads_errors():
        response = service.mutate_ad_group_bid_modifiers(
            request=_common.build_request(
                client, "MutateAdGroupBidModifiersRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
