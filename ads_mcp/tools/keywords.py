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

"""Tools for ad-group keywords (positive + negative) and campaign-level negatives."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common

_AGC_FIELDS = (
    "ad_group_criterion.criterion_id, ad_group_criterion.status, "
    "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
    "ad_group_criterion.cpc_bid_micros, ad_group_criterion.negative, "
    "ad_group_criterion.ad_group, ad_group_criterion.resource_name"
)
_CC_FIELDS = (
    "campaign_criterion.criterion_id, campaign_criterion.negative, "
    "campaign_criterion.keyword.text, campaign_criterion.keyword.match_type, "
    "campaign_criterion.campaign, campaign_criterion.resource_name"
)


def _match_type_enum(client, mt: str):
    return client.enums.KeywordMatchTypeEnum[mt.upper()]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_keywords(
    customer_id: str,
    ad_group_id: str | None = None,
    campaign_id: str | None = None,
    include_negatives: bool = True,
    status_filter: list[str] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Lists ad-group-level keywords.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Optional scope.
        campaign_id: Optional scope.
        include_negatives: If False, excludes ad-group negatives.
        status_filter: e.g. ['ENABLED','PAUSED','REMOVED'].
        limit: Max rows.
    """
    where = ["ad_group_criterion.type = KEYWORD"]
    if ad_group_id:
        where.append(f"ad_group.id = {int(ad_group_id)}")
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    if not include_negatives:
        where.append("ad_group_criterion.negative = FALSE")
    if status_filter:
        where.append(
            f"ad_group_criterion.status IN ({_common.comma_join(status_filter)})"
        )
    clause = " WHERE " + " AND ".join(where)
    query = (
        f"SELECT {_AGC_FIELDS} FROM ad_group_criterion{clause} "
        f"LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_campaign_negative_keywords(
    customer_id: str,
    campaign_id: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Lists campaign-level negative keywords."""
    where = [
        "campaign_criterion.type = KEYWORD",
        "campaign_criterion.negative = TRUE",
    ]
    if campaign_id:
        where.append(f"campaign.id = {int(campaign_id)}")
    clause = " WHERE " + " AND ".join(where)
    query = (
        f"SELECT {_CC_FIELDS} FROM campaign_criterion{clause} "
        f"LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def add_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds positive keywords to an ad group.

    Args:
        customer_id: 10-digit customer id.
        ad_group_id: Numeric ad group id.
        keywords: List of {text, match_type, cpc_bid_micros?}. match_type is one of
            'EXACT', 'PHRASE', 'BROAD'.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")

    operations = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = _common.ad_group_path(customer_id, ad_group_id)
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = kw["text"]
        c.keyword.match_type = _match_type_enum(client, kw["match_type"])
        if "cpc_bid_micros" in kw and kw["cpc_bid_micros"] is not None:
            c.cpc_bid_micros = int(kw["cpc_bid_micros"])
        operations.append(op)

    with _common.google_ads_errors():
        response = service.mutate_ad_group_criteria(
            request=_common.build_request(
                client, "MutateAdGroupCriteriaRequest",
                customer_id=customer_id,
                operations=operations,
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
def update_keyword(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    status: str | None = None,
    cpc_bid_micros: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates an ad-group keyword's status or CPC bid."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.update.resource_name = _common.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    if status is not None:
        op.update.status = client.enums.AdGroupCriterionStatusEnum[status]
        _common.set_field_mask(op, "status")
    if cpc_bid_micros is not None:
        op.update.cpc_bid_micros = int(cpc_bid_micros)
        _common.set_field_mask(op, "cpc_bid_micros")

    if not op.update_mask.paths:
        return {"dry_run": dry_run, "results": [], "note": "no fields to update"}

    with _common.google_ads_errors():
        response = service.mutate_ad_group_criteria(
            request=_common.build_request(
                client, "MutateAdGroupCriteriaRequest",
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
def remove_keyword(
    customer_id: str,
    ad_group_id: str,
    criterion_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes a keyword from an ad group. Irreversible."""
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.remove = _common.ad_group_criterion_path(
        customer_id, ad_group_id, criterion_id
    )
    with _common.google_ads_errors():
        response = service.mutate_ad_group_criteria(
            request=_common.build_request(
                client, "MutateAdGroupCriteriaRequest",
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
def add_ad_group_negative_keywords(
    customer_id: str,
    ad_group_id: str,
    keywords: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds negative keywords scoped to an ad group.

    Args:
        keywords: list of {text, match_type}.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    operations = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = _common.ad_group_path(customer_id, ad_group_id)
        c.negative = True
        c.keyword.text = kw["text"]
        c.keyword.match_type = _match_type_enum(client, kw["match_type"])
        operations.append(op)
    with _common.google_ads_errors():
        response = service.mutate_ad_group_criteria(
            request=_common.build_request(
                client, "MutateAdGroupCriteriaRequest",
                customer_id=customer_id,
                operations=operations,
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
def add_campaign_negative_keywords(
    customer_id: str,
    campaign_id: str,
    keywords: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds negative keywords scoped to a campaign.

    Args:
        keywords: list of {text, match_type}.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    operations = []
    for kw in keywords:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = _common.campaign_path(customer_id, campaign_id)
        c.negative = True
        c.keyword.text = kw["text"]
        c.keyword.match_type = _match_type_enum(client, kw["match_type"])
        operations.append(op)
    with _common.google_ads_errors():
        response = service.mutate_campaign_criteria(
            request=_common.build_request(
                client, "MutateCampaignCriteriaRequest",
                customer_id=customer_id,
                operations=operations,
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
def remove_campaign_criterion(
    customer_id: str,
    campaign_id: str,
    criterion_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Removes a campaign-level criterion (negative keyword, location, language, etc.)."""
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    op.remove = _common.campaign_criterion_path(
        customer_id, campaign_id, criterion_id
    )
    with _common.google_ads_errors():
        response = service.mutate_campaign_criteria(
            request=_common.build_request(
                client, "MutateCampaignCriteriaRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
