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

"""Tools for managing AdGroup resources."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common

_BASE_FIELDS = (
    "ad_group.id, ad_group.name, ad_group.status, ad_group.type, "
    "ad_group.cpc_bid_micros, ad_group.campaign, ad_group.resource_name"
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_ad_groups(
    customer_id: str,
    campaign_id: str | None = None,
    status_filter: list[str] | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Lists ad groups, optionally scoped to a campaign.

    Args:
        customer_id: 10-digit customer id.
        campaign_id: If set, only ad groups in this campaign.
        status_filter: e.g. ['ENABLED','PAUSED','REMOVED'].
        limit: Max rows.
    """
    where = []
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    if status_filter:
        where.append(f"ad_group.status IN ({_common.comma_join(status_filter)})")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    query = f"SELECT {_BASE_FIELDS} FROM ad_group{clause} LIMIT {int(limit)}"
    return _common.gaql_search(customer_id, query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_ad_group(customer_id: str, ad_group_id: str) -> list[dict[str, Any]]:
    """Returns one ad group by id."""
    query = (
        f"SELECT {_BASE_FIELDS} FROM ad_group "
        f"WHERE ad_group.id = {int(ad_group_id)} LIMIT 1"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_ad_group(
    customer_id: str,
    campaign_id: str,
    name: str,
    type: str = "SEARCH_STANDARD",
    cpc_bid_micros: int | None = None,
    status: str = "ENABLED",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates an AdGroup.

    Args:
        customer_id: 10-digit customer id.
        campaign_id: Numeric campaign id.
        name: Ad group name.
        type: 'SEARCH_STANDARD','DISPLAY_STANDARD','SHOPPING_PRODUCT_ADS','VIDEO_BUMPER',
              'SEARCH_DYNAMIC_ADS','VIDEO_NON_SKIPPABLE_IN_STREAM','VIDEO_TRUE_VIEW_IN_DISPLAY', etc.
        cpc_bid_micros: Default CPC bid in micros (only used for manual bidding).
        status: 'ENABLED' or 'PAUSED'.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.name = name
    ag.campaign = _common.campaign_path(customer_id, campaign_id)
    ag.status = client.enums.AdGroupStatusEnum[status]
    ag.type_ = client.enums.AdGroupTypeEnum[type]
    if cpc_bid_micros is not None:
        ag.cpc_bid_micros = int(cpc_bid_micros)

    with _common.google_ads_errors():
        response = service.mutate_ad_groups(
            request=_common.build_request(
                client, "MutateAdGroupsRequest",
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
def update_ad_group(
    customer_id: str,
    ad_group_id: str,
    name: str | None = None,
    status: str | None = None,
    cpc_bid_micros: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates assignable fields on an ad group."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = _common.ad_group_path(customer_id, ad_group_id)

    if name is not None:
        op.update.name = name
        _common.set_field_mask(op, "name")
    if status is not None:
        op.update.status = client.enums.AdGroupStatusEnum[status]
        _common.set_field_mask(op, "status")
    if cpc_bid_micros is not None:
        op.update.cpc_bid_micros = int(cpc_bid_micros)
        _common.set_field_mask(op, "cpc_bid_micros")

    if not op.update_mask.paths:
        return {"dry_run": dry_run, "results": [], "note": "no fields to update"}

    with _common.google_ads_errors():
        response = service.mutate_ad_groups(
            request=_common.build_request(
                client, "MutateAdGroupsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


def _set_status(
    customer_id: str, ad_group_id: str, status: str, dry_run: bool
) -> dict[str, Any]:
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = _common.ad_group_path(customer_id, ad_group_id)
    op.update.status = client.enums.AdGroupStatusEnum[status]
    _common.set_field_mask(op, "status")
    with _common.google_ads_errors():
        response = service.mutate_ad_groups(
            request=_common.build_request(
                client, "MutateAdGroupsRequest",
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
def pause_ad_group(
    customer_id: str, ad_group_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Sets an ad group to PAUSED."""
    return _set_status(customer_id, ad_group_id, "PAUSED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True)
)
def enable_ad_group(
    customer_id: str, ad_group_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Sets an ad group to ENABLED."""
    return _set_status(customer_id, ad_group_id, "ENABLED", dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def remove_ad_group(
    customer_id: str, ad_group_id: str, dry_run: bool = False
) -> dict[str, Any]:
    """Removes (deletes) an ad group. Irreversible."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    op.remove = _common.ad_group_path(customer_id, ad_group_id)
    with _common.google_ads_errors():
        response = service.mutate_ad_groups(
            request=_common.build_request(
                client, "MutateAdGroupsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
