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

"""Geo + language targeting helpers."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_geo_target_constants(
    queries: list[str],
    locale: str = "en",
    country_code: str | None = None,
) -> list[dict[str, Any]]:
    """Find geo_target_constants by free-text query (e.g. ['Mumbai','New York']).

    Args:
        queries: location names to look up.
        locale: BCP-47 language for the response (e.g. 'en').
        country_code: optional 2-letter ISO country to bias (e.g. 'IN').
    """
    client = utils.get_googleads_client()
    service = client.get_service("GeoTargetConstantService")
    request = client.get_type("SuggestGeoTargetConstantsRequest")
    request.locale = locale
    if country_code:
        request.country_code = country_code
    request.location_names.names.extend(queries)

    with _common.google_ads_errors():
        response = service.suggest_geo_target_constants(request=request)

    out = []
    for sugg in response.geo_target_constant_suggestions:
        gtc = sugg.geo_target_constant
        out.append(
            {
                "id": gtc.id,
                "resource_name": gtc.resource_name,
                "name": gtc.name,
                "country_code": gtc.country_code,
                "target_type": gtc.target_type,
                "status": gtc.status.name if gtc.status else None,
                "canonical_name": gtc.canonical_name,
                "search_term": sugg.search_term,
                "reach": sugg.reach,
                "locale": sugg.locale,
            }
        )
    return out


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def add_campaign_location_targets(
    customer_id: str,
    campaign_id: str,
    geo_target_constant_ids: list[str],
    negative: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds geo (location) targeting criteria to a campaign.

    Args:
        customer_id: 10-digit customer id.
        campaign_id: Numeric campaign id.
        geo_target_constant_ids: List of numeric geo target IDs (use
            search_geo_target_constants to discover them).
        negative: True to exclude these locations instead of including them.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    operations = []
    for gid in geo_target_constant_ids:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = _common.campaign_path(customer_id, campaign_id)
        c.location.geo_target_constant = _common.geo_target_constant_path(gid)
        c.negative = bool(negative)
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
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def add_campaign_language_targets(
    customer_id: str,
    campaign_id: str,
    language_constant_ids: list[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Adds language targeting criteria to a campaign.

    Common language IDs: 1000=English, 1019=Hindi, 1003=Spanish, 1002=French.
    Full list: https://developers.google.com/google-ads/api/data/codes-formats#languages
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    operations = []
    for lid in language_constant_ids:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = _common.campaign_path(customer_id, campaign_id)
        c.language.language_constant = _common.language_constant_path(lid)
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
