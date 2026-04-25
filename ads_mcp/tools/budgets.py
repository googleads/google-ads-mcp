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

"""Tools for managing CampaignBudget resources."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_budgets(customer_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Lists CampaignBudgets in the account.

    Args:
        customer_id: 10-digit customer id, no hyphens.
        limit: Max rows to return.
    """
    query = (
        "SELECT campaign_budget.id, campaign_budget.name, "
        "campaign_budget.amount_micros, campaign_budget.delivery_method, "
        "campaign_budget.explicitly_shared, campaign_budget.status, "
        "campaign_budget.resource_name "
        f"FROM campaign_budget LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_campaign_budget(
    customer_id: str,
    name: str,
    amount: float,
    delivery_method: str = "STANDARD",
    explicitly_shared: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a CampaignBudget.

    Args:
        customer_id: 10-digit customer id.
        name: Unique budget name.
        amount: Daily budget in account currency (e.g. 50.0 = $50/day).
        delivery_method: 'STANDARD' or 'ACCELERATED'.
        explicitly_shared: True to allow attaching to multiple campaigns.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignBudgetService")

    op = client.get_type("CampaignBudgetOperation")
    budget = op.create
    budget.name = name
    budget.amount_micros = _common.micros(amount)
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum[
        delivery_method
    ]
    budget.explicitly_shared = explicitly_shared

    with _common.google_ads_errors():
        response = service.mutate_campaign_budgets(
            request=_common.build_request(
                client, "MutateCampaignBudgetsRequest",
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
def update_campaign_budget(
    customer_id: str,
    budget_id: str,
    amount: float | None = None,
    name: str | None = None,
    delivery_method: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Updates a CampaignBudget. Only provided fields are changed.

    Args:
        customer_id: 10-digit customer id.
        budget_id: Numeric budget id.
        amount: New daily budget in account currency.
        name: New budget name.
        delivery_method: 'STANDARD' or 'ACCELERATED'.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("CampaignBudgetService")

    op = client.get_type("CampaignBudgetOperation")
    budget = op.update
    budget.resource_name = _common.campaign_budget_path(customer_id, budget_id)

    if amount is not None:
        budget.amount_micros = _common.micros(amount)
        _common.set_field_mask(op, "amount_micros")
    if name is not None:
        budget.name = name
        _common.set_field_mask(op, "name")
    if delivery_method is not None:
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum[
            delivery_method
        ]
        _common.set_field_mask(op, "delivery_method")

    if not op.update_mask.paths:
        return {"dry_run": dry_run, "results": [], "note": "no fields to update"}

    with _common.google_ads_errors():
        response = service.mutate_campaign_budgets(
            request=_common.build_request(
                client, "MutateCampaignBudgetsRequest",
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
def remove_campaign_budget(
    customer_id: str,
    budget_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Deletes a CampaignBudget. Will fail if any campaign still references it."""
    client = utils.get_googleads_client()
    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    op.remove = _common.campaign_budget_path(customer_id, budget_id)
    with _common.google_ads_errors():
        response = service.mutate_campaign_budgets(
            request=_common.build_request(
                client, "MutateCampaignBudgetsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
