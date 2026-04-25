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

"""Portfolio bidding strategy tools.

Portfolio strategies are reusable across campaigns. Create one here, then set
a campaign to use it via update_campaign (or via a separate
bidding_strategy field on create_search_campaign in a future revision).
"""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


def _bidding_strategy_path(customer_id: str, strategy_id: str | int) -> str:
    return f"customers/{customer_id}/biddingStrategies/{strategy_id}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_bidding_strategies(
    customer_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Lists portfolio bidding strategies in the account."""
    query = (
        "SELECT bidding_strategy.id, bidding_strategy.name, "
        "bidding_strategy.type, bidding_strategy.status, "
        "bidding_strategy.currency_code, bidding_strategy.resource_name, "
        "bidding_strategy.target_cpa.target_cpa_micros, "
        "bidding_strategy.target_roas.target_roas, "
        "bidding_strategy.maximize_conversions.target_cpa_micros, "
        "bidding_strategy.maximize_conversion_value.target_roas "
        f"FROM bidding_strategy LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


def _create(customer_id: str, op, dry_run: bool) -> dict[str, Any]:
    client = utils.get_googleads_client()
    service = client.get_service("BiddingStrategyService")
    with _common.google_ads_errors():
        response = service.mutate_bidding_strategies(
            request=_common.build_request(
                client, "MutateBiddingStrategiesRequest",
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
def create_portfolio_target_cpa(
    customer_id: str,
    name: str,
    target_cpa_micros: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a reusable Target CPA bidding strategy."""
    client = utils.get_googleads_client()
    op = client.get_type("BiddingStrategyOperation")
    b = op.create
    b.name = name
    b.target_cpa.target_cpa_micros = int(target_cpa_micros)
    return _create(customer_id, op, dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_portfolio_target_roas(
    customer_id: str,
    name: str,
    target_roas: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a reusable Target ROAS bidding strategy. target_roas is a ratio (e.g. 4.0 = 400%)."""
    client = utils.get_googleads_client()
    op = client.get_type("BiddingStrategyOperation")
    b = op.create
    b.name = name
    b.target_roas.target_roas = float(target_roas)
    return _create(customer_id, op, dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_portfolio_maximize_conversions(
    customer_id: str,
    name: str,
    target_cpa_micros: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a reusable MaximizeConversions strategy, optionally with a target CPA."""
    client = utils.get_googleads_client()
    op = client.get_type("BiddingStrategyOperation")
    b = op.create
    b.name = name
    if target_cpa_micros is not None:
        b.maximize_conversions.target_cpa_micros = int(target_cpa_micros)
    else:
        b.maximize_conversions  # touch to instantiate
    return _create(customer_id, op, dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_portfolio_maximize_conversion_value(
    customer_id: str,
    name: str,
    target_roas: float | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a reusable MaximizeConversionValue strategy, optionally with a target ROAS."""
    client = utils.get_googleads_client()
    op = client.get_type("BiddingStrategyOperation")
    b = op.create
    b.name = name
    if target_roas is not None:
        b.maximize_conversion_value.target_roas = float(target_roas)
    else:
        b.maximize_conversion_value
    return _create(customer_id, op, dry_run)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def update_bidding_strategy(
    customer_id: str,
    strategy_id: str,
    name: str | None = None,
    target_cpa_micros: int | None = None,
    target_roas: float | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates a portfolio bidding strategy. Only the fields relevant to the
    strategy's type can be updated (e.g. target_cpa_micros on a TargetCpa
    strategy; target_roas on a TargetRoas / MaxConversionValue strategy).
    """
    client = utils.get_googleads_client()
    service = client.get_service("BiddingStrategyService")
    op = client.get_type("BiddingStrategyOperation")
    op.update.resource_name = _bidding_strategy_path(customer_id, strategy_id)

    if name is not None:
        op.update.name = name
        _common.set_field_mask(op, "name")
    if target_cpa_micros is not None:
        op.update.target_cpa.target_cpa_micros = int(target_cpa_micros)
        _common.set_field_mask(op, "target_cpa.target_cpa_micros")
        # Also support MaximizeConversions.target_cpa_micros variant — safe to
        # set both masks; the API ignores whichever doesn't apply to this type.
        op.update.maximize_conversions.target_cpa_micros = int(target_cpa_micros)
        _common.set_field_mask(op, "maximize_conversions.target_cpa_micros")
    if target_roas is not None:
        op.update.target_roas.target_roas = float(target_roas)
        _common.set_field_mask(op, "target_roas.target_roas")
        op.update.maximize_conversion_value.target_roas = float(target_roas)
        _common.set_field_mask(
            op, "maximize_conversion_value.target_roas"
        )

    if not op.update_mask.paths:
        return {"dry_run": dry_run, "results": [], "note": "no fields to update"}

    with _common.google_ads_errors():
        response = service.mutate_bidding_strategies(
            request=_common.build_request(
                client, "MutateBiddingStrategiesRequest",
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
def set_campaign_bidding_strategy(
    customer_id: str,
    campaign_id: str,
    strategy_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Points a campaign at a portfolio bidding strategy.

    After this, the campaign's bidding behavior is inherited from the
    portfolio strategy. Any inline bidding strategy (e.g. a per-campaign
    MaxConversions target_cpa) is overridden.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = _common.campaign_path(customer_id, campaign_id)
    op.update.bidding_strategy = _bidding_strategy_path(
        customer_id, strategy_id
    )
    _common.set_field_mask(op, "bidding_strategy")
    with _common.google_ads_errors():
        response = service.mutate_campaigns(
            request=_common.build_request(
                client, "MutateCampaignsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
