"""Safe campaign management tools."""

from enum import Enum

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp import propose_and_confirm as pac
from ads_mcp import utils

campaigns_mcp = FastMCP("campaigns")


class CampaignOperation(str, Enum):
    """Supported campaign mutations."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


def _campaign_status(client, status: str):
    try:
        return client.get_type("CampaignStatusEnum").CampaignStatus[
            status.upper()
        ]
    except KeyError as exc:
        raise ToolError(
            "Error: status must be one of ENABLED, PAUSED, or REMOVED."
        ) from exc


@campaigns_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def manage_campaign(
    customer_id: str | int,
    operation: CampaignOperation,
    campaign_id: str | None = None,
    name: str | None = None,
    status: str | None = None,
    advertising_channel_type: str | None = None,
    daily_budget_micros: int | None = None,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
    validate_only: bool = True,
    checksum: str | None = None,
) -> str:
    """Creates, updates, or removes a campaign with propose-and-confirm.

    Creation requires name, advertising_channel_type, and daily_budget_micros.
    Updates require campaign_id and at least one mutable field (name or status).
    All calls validate by default; a commit requires the checksum returned by
    an identical validation call.
    """
    customer = utils.clean_customer_id(customer_id)
    if not customer:
        raise ToolError("Error: customer_id must contain digits.")
    action = operation.value if isinstance(operation, Enum) else str(operation)
    action = action.upper()
    if action not in CampaignOperation.__members__:
        raise ToolError("Error: operation must be CREATE, UPDATE, or REMOVE.")
    if action in ("UPDATE", "REMOVE") and not campaign_id:
        raise ToolError(f"Error: campaign_id is required for {action}.")
    if action == "CREATE":
        if not name or not advertising_channel_type or not daily_budget_micros:
            raise ToolError(
                "Error: CREATE requires name, advertising_channel_type, and "
                "daily_budget_micros."
            )
        if daily_budget_micros <= 0:
            raise ToolError("Error: daily_budget_micros must be positive.")
    if action == "UPDATE" and name is None and status is None:
        raise ToolError("Error: UPDATE requires name or status.")

    payload = {
        "tool": "manage_campaign",
        "operation": action,
        "campaign_id": campaign_id,
        "name": name,
        "status": status.upper() if status else None,
        "advertising_channel_type": (
            advertising_channel_type.upper()
            if advertising_channel_type
            else None
        ),
        "daily_budget_micros": daily_budget_micros,
        "login_customer_id": (
            str(login_customer_id) if login_customer_id else None
        ),
        "account_name": account_name,
    }
    changes = pac.build_change_items(
        action,
        "Campaign",
        campaign_id or name or "",
        {
            "Campaign ID": campaign_id,
            "Name": name,
            "Status": status.upper() if status else None,
            "Channel": (
                advertising_channel_type.upper()
                if advertising_channel_type
                else None
            ),
            "Daily Budget Micros": daily_budget_micros,
        },
    )
    client = utils.get_googleads_client(
        login_customer_id=login_customer_id, account_name=account_name
    )
    service = utils.get_googleads_service_from_client(
        client, "GoogleAdsService"
    )
    request = client.get_type("MutateGoogleAdsRequest")
    request.customer_id = customer
    if action == "CREATE":
        budget_name = f"customers/{customer}/campaignBudgets/-1"
        budget_mutate = client.get_type("MutateOperation")
        budget = budget_mutate.campaign_budget_operation.create
        budget.name = f"{name} budget"
        budget.amount_micros = daily_budget_micros
        budget.delivery_method = client.get_type(
            "BudgetDeliveryMethodEnum"
        ).BudgetDeliveryMethod.STANDARD
        campaign_mutate = client.get_type("MutateOperation")
        campaign = campaign_mutate.campaign_operation.create
        campaign.name = name
        campaign.campaign_budget = budget_name
        try:
            campaign.advertising_channel_type = client.get_type(
                "AdvertisingChannelTypeEnum"
            ).AdvertisingChannelType[advertising_channel_type.upper()]
        except KeyError as exc:
            raise ToolError(
                f"Error: invalid advertising_channel_type '{advertising_channel_type}'."
            ) from exc
        request.mutate_operations.extend([budget_mutate, campaign_mutate])
    elif action == "UPDATE":
        mutate = client.get_type("MutateOperation")
        campaign = mutate.campaign_operation.update
        campaign.resource_name = f"customers/{customer}/campaigns/{campaign_id}"
        paths = []
        if name is not None:
            campaign.name = name
            paths.append("name")
        if status is not None:
            campaign.status = _campaign_status(client, status)
            paths.append("status")
        mutate.campaign_operation.update_mask.paths.extend(paths)
        request.mutate_operations.append(mutate)
    else:
        mutate = client.get_type("MutateOperation")
        mutate.campaign_operation.remove = (
            f"customers/{customer}/campaigns/{campaign_id}"
        )
        request.mutate_operations.append(mutate)

    def validate():
        request.validate_only = True
        service.mutate(request=request)

    def commit() -> str:
        request.validate_only = False
        service.mutate(request=request)
        action_past = {
            "CREATE": "created",
            "UPDATE": "updated",
            "REMOVE": "removed",
        }[action]
        return f"Successfully {action_past} campaign."

    return pac.propose_and_confirm(
        customer_id=customer,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=payload,
        change_items=changes,
        validate_fn=validate,
        commit_fn=commit,
        error_prefix=f"Failed to {action.lower()} campaign",
    )
