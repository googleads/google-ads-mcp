# Copyright 2026 Rodrigo Palma.
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

"""Tools for modifying campaigns, ad groups, ads, keywords and budgets.

These tools are disabled by default. They are exposed only when the `mutate`
namespace is enabled in the tools configuration (see tools_config_write.yaml).

Every tool only validates its change unless the caller passes
validate_only=False, so agents can show the user what will change first.
"""

import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Literal, NamedTuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.field_mask_pb2 import FieldMask
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor

mutate_mcp = FastMCP("mutate")

# Limits on how much a single call may raise a budget or a bid, as a percentage
# of the current value. They are read from the server environment so that
# agents cannot override them.
MAX_BUDGET_INCREASE_ENV_VAR = "GOOGLE_ADS_MCP_MAX_BUDGET_INCREASE_PERCENT"
MAX_BID_INCREASE_ENV_VAR = "GOOGLE_ADS_MCP_MAX_BID_INCREASE_PERCENT"
DEFAULT_MAX_INCREASE_PERCENT = 50.0

MAX_NEGATIVE_KEYWORDS_PER_CALL = 100

# Bidding strategies that use the max CPC bids set on ad groups and keywords.
_CPC_BIDDING_STRATEGIES = ("MANUAL_CPC", "ENHANCED_CPC")

_UPDATE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True
)
_CREATE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False
)

_VALIDATED_MESSAGE = (
    "Validation succeeded and nothing was changed. Show these changes to the "
    "user and call the tool again with validate_only=false only after they "
    "confirm them."
)
_APPLIED_MESSAGE = "The changes were applied."


class _MutateTarget(NamedTuple):
    operation_type: str
    service_name: str
    method_name: str
    request_type: str


_MUTATE_TARGETS = {
    "campaign": _MutateTarget(
        "CampaignOperation",
        "CampaignService",
        "mutate_campaigns",
        "MutateCampaignsRequest",
    ),
    "ad_group": _MutateTarget(
        "AdGroupOperation",
        "AdGroupService",
        "mutate_ad_groups",
        "MutateAdGroupsRequest",
    ),
    "ad_group_ad": _MutateTarget(
        "AdGroupAdOperation",
        "AdGroupAdService",
        "mutate_ad_group_ads",
        "MutateAdGroupAdsRequest",
    ),
    "campaign_budget": _MutateTarget(
        "CampaignBudgetOperation",
        "CampaignBudgetService",
        "mutate_campaign_budgets",
        "MutateCampaignBudgetsRequest",
    ),
    "campaign_criterion": _MutateTarget(
        "CampaignCriterionOperation",
        "CampaignCriterionService",
        "mutate_campaign_criteria",
        "MutateCampaignCriteriaRequest",
    ),
    "ad_group_criterion": _MutateTarget(
        "AdGroupCriterionOperation",
        "AdGroupCriterionService",
        "mutate_ad_group_criteria",
        "MutateAdGroupCriteriaRequest",
    ),
}


def _clean_id(value: str | int, name: str) -> str:
    """Strips non-digit characters from an id and rejects empty results."""
    cleaned = utils.clean_customer_id(value)
    if not cleaned:
        raise ToolError(f"{name} must be a numeric id, got {value!r}.")
    return cleaned


def _to_micros(amount: float, name: str) -> int:
    """Converts an amount in the account currency to micros, rounded to cents."""
    # Decimal avoids float artifacts such as 12.345 * 100 == 1234.4999...
    cents = Decimal(str(amount)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    micros = int(cents * 1_000_000)
    if micros <= 0:
        raise ToolError(f"{name} must be greater than zero, got {amount}.")
    return micros


def _from_micros(micros: int) -> float:
    return micros / 1_000_000


def _max_increase_percent(env_var: str) -> float:
    raw_value = os.environ.get(env_var)
    if not raw_value:
        return DEFAULT_MAX_INCREASE_PERCENT
    try:
        value = float(raw_value)
    except ValueError:
        raise ToolError(f"{env_var} must be a number, got {raw_value!r}.")
    if value < 0:
        raise ToolError(f"{env_var} cannot be negative, got {raw_value!r}.")
    return value


def _check_increase(
    current_micros: int, new_micros: int, env_var: str, what: str
) -> None:
    """Rejects increases larger than the limit set in `env_var`.

    Decreases are always allowed, and so is setting a value that had none.
    """
    if current_micros <= 0 or new_micros <= current_micros:
        return
    increase = (new_micros - current_micros) / current_micros * 100
    limit = _max_increase_percent(env_var)
    if increase > limit:
        raise ToolError(
            f"This raises the {what} by {increase:.0f}%, more than the "
            f"{limit:g}% this server allows in a single change. Make a "
            f"smaller change, or ask the server administrator to raise "
            f"{env_var}."
        )


def _get_service(client: GoogleAdsClient, service_name: str):
    return client.get_service(
        service_name, interceptors=[MCPHeaderInterceptor()]
    )


def _raise_tool_error(ex: GoogleAdsException) -> None:
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    raise ToolError(
        f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)
    ) from ex


def _find_one(
    client: GoogleAdsClient, customer_id: str, query: str, not_found: str
):
    """Runs a GAQL query and returns its first row."""
    ga_service = _get_service(client, "GoogleAdsService")
    try:
        rows = list(ga_service.search(customer_id=customer_id, query=query))
    except GoogleAdsException as ex:
        _raise_tool_error(ex)
    if not rows:
        raise ToolError(not_found)
    return rows[0]


def _update_operation(
    client: GoogleAdsClient, target: str, resource_name: str, **fields: Any
):
    """Builds an operation that updates only the given fields of a resource."""
    operation = client.get_type(_MUTATE_TARGETS[target].operation_type)
    operation.update.resource_name = resource_name
    for field_name, value in fields.items():
        setattr(operation.update, field_name, value)
    client.copy_from(operation.update_mask, FieldMask(paths=list(fields)))
    return operation


def _send(
    client: GoogleAdsClient,
    target: str,
    customer_id: str,
    operations: List[Any],
    validate_only: bool,
) -> List[str]:
    """Sends the operations and returns the resource names of the results."""
    mutate_target = _MUTATE_TARGETS[target]
    request = client.get_type(mutate_target.request_type)
    request.customer_id = customer_id
    request.operations.extend(operations)
    request.validate_only = validate_only
    service = _get_service(client, mutate_target.service_name)
    try:
        response = getattr(service, mutate_target.method_name)(request=request)
    except GoogleAdsException as ex:
        _raise_tool_error(ex)
    return [result.resource_name for result in response.results]


def _current_user() -> str:
    """Returns the email of the authenticated user, or 'local' in stdio mode."""
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()
    if token and token.claims.get("email"):
        return token.claims["email"]
    return "local"


def _result(
    tool_name: str,
    customer_id: str,
    validate_only: bool,
    changes: List[Dict[str, Any]],
    resource_names: List[str],
    warnings: List[str] | None = None,
) -> Dict[str, Any]:
    """Logs the call for auditing and builds the tool response."""
    utils.logger.info(
        f"ads_mcp.mutate tool={tool_name} user={_current_user()} "
        f"customer_id={customer_id} validate_only={validate_only} "
        f"changes={changes}"
    )
    result: Dict[str, Any] = {
        "applied": not validate_only,
        "message": _VALIDATED_MESSAGE if validate_only else _APPLIED_MESSAGE,
        "changes": changes,
    }
    if resource_names:
        result["resource_names"] = resource_names
    if warnings:
        result["warnings"] = warnings
    return result


def _bidding_warnings(bidding_strategy_type) -> List[str]:
    if bidding_strategy_type.name in _CPC_BIDDING_STRATEGIES:
        return []
    return [
        f"The campaign uses {bidding_strategy_type.name} bidding, which does "
        "not use max CPC bids, so this change may have no effect."
    ]


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def set_campaign_status(
    customer_id: str | int,
    campaign_id: str | int,
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pauses or enables a campaign.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the campaign.
        campaign_id: The id of the campaign (campaign.id).
        status: The new status of the campaign.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    campaign_id = _clean_id(campaign_id, "campaign_id")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT campaign.resource_name, campaign.name, campaign.status "
        f"FROM campaign WHERE campaign.id = {campaign_id}",
        f"Campaign {campaign_id} was not found in customer {customer_id}.",
    )
    operation = _update_operation(
        client,
        "campaign",
        row.campaign.resource_name,
        status=client.enums.CampaignStatusEnum[status],
    )
    resource_names = _send(
        client, "campaign", customer_id, [operation], validate_only
    )
    return _result(
        "set_campaign_status",
        customer_id,
        validate_only,
        [
            {
                "resource_name": row.campaign.resource_name,
                "campaign": row.campaign.name,
                "status": {"from": row.campaign.status.name, "to": status},
            }
        ],
        resource_names,
    )


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def set_ad_group_status(
    customer_id: str | int,
    ad_group_id: str | int,
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pauses or enables an ad group.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the ad group.
        ad_group_id: The id of the ad group (ad_group.id).
        status: The new status of the ad group.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    ad_group_id = _clean_id(ad_group_id, "ad_group_id")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT ad_group.resource_name, ad_group.name, ad_group.status, "
        f"campaign.name FROM ad_group WHERE ad_group.id = {ad_group_id}",
        f"Ad group {ad_group_id} was not found in customer {customer_id}.",
    )
    operation = _update_operation(
        client,
        "ad_group",
        row.ad_group.resource_name,
        status=client.enums.AdGroupStatusEnum[status],
    )
    resource_names = _send(
        client, "ad_group", customer_id, [operation], validate_only
    )
    return _result(
        "set_ad_group_status",
        customer_id,
        validate_only,
        [
            {
                "resource_name": row.ad_group.resource_name,
                "campaign": row.campaign.name,
                "ad_group": row.ad_group.name,
                "status": {"from": row.ad_group.status.name, "to": status},
            }
        ],
        resource_names,
    )


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def set_ad_status(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_id: str | int,
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Pauses or enables an ad in an ad group.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the ad.
        ad_group_id: The id of the ad group that contains the ad (ad_group.id).
        ad_id: The id of the ad (ad_group_ad.ad.id).
        status: The new status of the ad.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    ad_group_id = _clean_id(ad_group_id, "ad_group_id")
    ad_id = _clean_id(ad_id, "ad_id")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT ad_group_ad.resource_name, ad_group_ad.status, "
        "ad_group_ad.ad.name, ad_group_ad.ad.type, ad_group.name "
        f"FROM ad_group_ad WHERE ad_group.id = {ad_group_id} "
        f"AND ad_group_ad.ad.id = {ad_id}",
        f"Ad {ad_id} was not found in ad group {ad_group_id} of customer "
        f"{customer_id}.",
    )
    operation = _update_operation(
        client,
        "ad_group_ad",
        row.ad_group_ad.resource_name,
        status=client.enums.AdGroupAdStatusEnum[status],
    )
    resource_names = _send(
        client, "ad_group_ad", customer_id, [operation], validate_only
    )
    return _result(
        "set_ad_status",
        customer_id,
        validate_only,
        [
            {
                "resource_name": row.ad_group_ad.resource_name,
                "ad_group": row.ad_group.name,
                "ad_name": row.ad_group_ad.ad.name,
                "ad_type": row.ad_group_ad.ad.type_.name,
                "status": {"from": row.ad_group_ad.status.name, "to": status},
            }
        ],
        resource_names,
    )


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def update_campaign_budget(
    customer_id: str | int,
    campaign_id: str | int,
    daily_amount: float,
    allow_shared_budget: bool = False,
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Changes the daily budget of a campaign.

    The amount is in the account currency, not in micros: 25.5 means 25.50.
    It is rounded to cents. The server rejects increases above a configured
    percentage of the current budget (50% by default); decreases are always
    allowed.

    If the budget is shared with other campaigns, changing it changes all of
    them, so the call is rejected unless allow_shared_budget is true. Only set
    it after the user confirms they want to change the shared budget.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the campaign.
        campaign_id: The id of the campaign (campaign.id).
        daily_amount: The new daily budget in the account currency.
        allow_shared_budget: Allows changing a budget shared by several campaigns.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    campaign_id = _clean_id(campaign_id, "campaign_id")
    new_amount_micros = _to_micros(daily_amount, "daily_amount")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT campaign.name, campaign_budget.resource_name, "
        "campaign_budget.amount_micros, campaign_budget.period, "
        "campaign_budget.explicitly_shared, campaign_budget.reference_count, "
        f"customer.currency_code FROM campaign WHERE campaign.id = {campaign_id}",
        f"Campaign {campaign_id} was not found in customer {customer_id}.",
    )
    budget = row.campaign_budget
    if budget.period.name != "DAILY":
        raise ToolError(
            f"The budget of campaign {campaign_id} has period "
            f"{budget.period.name}; only daily budgets can be changed."
        )
    if budget.explicitly_shared and not allow_shared_budget:
        raise ToolError(
            f"The budget of campaign {campaign_id} is shared by "
            f"{budget.reference_count} campaigns, and changing it changes all "
            "of them. Confirm with the user, then call again with "
            "allow_shared_budget=true."
        )
    _check_increase(
        budget.amount_micros,
        new_amount_micros,
        MAX_BUDGET_INCREASE_ENV_VAR,
        "daily budget",
    )

    operation = _update_operation(
        client,
        "campaign_budget",
        budget.resource_name,
        amount_micros=new_amount_micros,
    )
    resource_names = _send(
        client, "campaign_budget", customer_id, [operation], validate_only
    )
    return _result(
        "update_campaign_budget",
        customer_id,
        validate_only,
        [
            {
                "resource_name": budget.resource_name,
                "campaign": row.campaign.name,
                "currency": row.customer.currency_code,
                "shared_by_campaigns": budget.reference_count,
                "daily_amount": {
                    "from": _from_micros(budget.amount_micros),
                    "to": _from_micros(new_amount_micros),
                },
            }
        ],
        resource_names,
    )


@mutate_mcp.tool(annotations=_CREATE_ANNOTATIONS)
def add_negative_keywords(
    customer_id: str | int,
    keywords: List[str],
    match_type: Literal["EXACT", "PHRASE", "BROAD"],
    campaign_id: str | int | None = None,
    ad_group_id: str | int | None = None,
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Adds negative keywords to a campaign or to an ad group.

    Give exactly one of campaign_id or ad_group_id. Match types for negative
    keywords: EXACT blocks only searches equal to the keyword, PHRASE blocks
    searches that contain the keyword's words in order, and BROAD blocks
    searches that contain all of the keyword's words in any order.

    Duplicate keywords in the list are sent once. All keywords are added or,
    if any of them fails, none is.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the campaign or ad group.
        keywords: The keyword texts to exclude, at most 100 per call.
        match_type: The match type applied to all of the keywords.
        campaign_id: The id of the campaign to add the keywords to.
        ad_group_id: The id of the ad group to add the keywords to.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    if (campaign_id is None) == (ad_group_id is None):
        raise ToolError("Give exactly one of campaign_id or ad_group_id.")

    texts = []
    seen = set()
    for keyword in keywords:
        text = " ".join(keyword.split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            texts.append(text)
    if not texts:
        raise ToolError("keywords must contain at least one keyword.")
    if len(texts) > MAX_NEGATIVE_KEYWORDS_PER_CALL:
        raise ToolError(
            f"At most {MAX_NEGATIVE_KEYWORDS_PER_CALL} keywords can be added "
            f"per call, got {len(texts)}."
        )

    customer_id = _clean_id(customer_id, "customer_id")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    if campaign_id is not None:
        campaign_id = _clean_id(campaign_id, "campaign_id")
        row = _find_one(
            client,
            customer_id,
            "SELECT campaign.resource_name, campaign.name FROM campaign "
            f"WHERE campaign.id = {campaign_id}",
            f"Campaign {campaign_id} was not found in customer {customer_id}.",
        )
        target, parent_field = "campaign_criterion", "campaign"
        parent_resource_name = row.campaign.resource_name
        change = {"level": "campaign", "campaign": row.campaign.name}
    else:
        ad_group_id = _clean_id(ad_group_id, "ad_group_id")
        row = _find_one(
            client,
            customer_id,
            "SELECT ad_group.resource_name, ad_group.name, campaign.name "
            f"FROM ad_group WHERE ad_group.id = {ad_group_id}",
            f"Ad group {ad_group_id} was not found in customer {customer_id}.",
        )
        target, parent_field = "ad_group_criterion", "ad_group"
        parent_resource_name = row.ad_group.resource_name
        change = {
            "level": "ad_group",
            "campaign": row.campaign.name,
            "ad_group": row.ad_group.name,
        }

    operations = []
    for text in texts:
        operation = client.get_type(_MUTATE_TARGETS[target].operation_type)
        criterion = operation.create
        setattr(criterion, parent_field, parent_resource_name)
        criterion.negative = True
        criterion.keyword.text = text
        criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum[
            match_type
        ]
        operations.append(operation)

    resource_names = _send(
        client, target, customer_id, operations, validate_only
    )
    change.update(
        {
            "resource_name": parent_resource_name,
            "match_type": match_type,
            "negative_keywords_added": texts,
        }
    )
    return _result(
        "add_negative_keywords",
        customer_id,
        validate_only,
        [change],
        resource_names,
    )


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def set_ad_group_cpc_bid(
    customer_id: str | int,
    ad_group_id: str | int,
    cpc_bid: float,
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Sets the default max CPC bid of an ad group.

    The bid is in the account currency, not in micros: 1.5 means 1.50. It is
    rounded to cents. Keywords without their own bid use this one. Max CPC
    bids only take effect with manual CPC bidding. The server rejects
    increases above a configured percentage of the current bid (50% by
    default); decreases are always allowed.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the ad group.
        ad_group_id: The id of the ad group (ad_group.id).
        cpc_bid: The new max CPC bid in the account currency.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    ad_group_id = _clean_id(ad_group_id, "ad_group_id")
    new_bid_micros = _to_micros(cpc_bid, "cpc_bid")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT ad_group.resource_name, ad_group.name, "
        "ad_group.cpc_bid_micros, campaign.name, "
        "campaign.bidding_strategy_type, customer.currency_code "
        f"FROM ad_group WHERE ad_group.id = {ad_group_id}",
        f"Ad group {ad_group_id} was not found in customer {customer_id}.",
    )
    _check_increase(
        row.ad_group.cpc_bid_micros,
        new_bid_micros,
        MAX_BID_INCREASE_ENV_VAR,
        "max CPC bid",
    )

    operation = _update_operation(
        client,
        "ad_group",
        row.ad_group.resource_name,
        cpc_bid_micros=new_bid_micros,
    )
    resource_names = _send(
        client, "ad_group", customer_id, [operation], validate_only
    )
    return _result(
        "set_ad_group_cpc_bid",
        customer_id,
        validate_only,
        [
            {
                "resource_name": row.ad_group.resource_name,
                "campaign": row.campaign.name,
                "ad_group": row.ad_group.name,
                "currency": row.customer.currency_code,
                "cpc_bid": {
                    "from": _from_micros(row.ad_group.cpc_bid_micros),
                    "to": _from_micros(new_bid_micros),
                },
            }
        ],
        resource_names,
        _bidding_warnings(row.campaign.bidding_strategy_type),
    )


@mutate_mcp.tool(annotations=_UPDATE_ANNOTATIONS)
def set_keyword_cpc_bid(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    cpc_bid: float,
    validate_only: bool = True,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Sets the max CPC bid of a keyword.

    The bid is in the account currency, not in micros: 1.5 means 1.50. It is
    rounded to cents. Find criterion ids with the search tool, for example
    selecting ad_group_criterion.criterion_id from keyword_view. Max CPC bids
    only take effect with manual CPC bidding. The server rejects increases
    above a configured percentage of the current bid (50% by default), using
    the ad group bid when the keyword has none; decreases are always allowed.

    By default the change is only validated, not applied. Show the returned
    changes to the user and call again with validate_only=false only after
    they confirm.

    Args:
        customer_id: The id of the customer that owns the keyword.
        ad_group_id: The id of the ad group that contains the keyword (ad_group.id).
        criterion_id: The id of the keyword (ad_group_criterion.criterion_id).
        cpc_bid: The new max CPC bid in the account currency.
        validate_only: If true, validates the change without applying it.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
    """
    customer_id = _clean_id(customer_id, "customer_id")
    ad_group_id = _clean_id(ad_group_id, "ad_group_id")
    criterion_id = _clean_id(criterion_id, "criterion_id")
    new_bid_micros = _to_micros(cpc_bid, "cpc_bid")
    client = utils.get_googleads_client(login_customer_id=login_customer_id)

    row = _find_one(
        client,
        customer_id,
        "SELECT ad_group_criterion.resource_name, "
        "ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type, "
        "ad_group_criterion.negative, ad_group_criterion.cpc_bid_micros, "
        "ad_group_criterion.effective_cpc_bid_micros, ad_group.name, "
        "campaign.bidding_strategy_type, customer.currency_code "
        f"FROM ad_group_criterion WHERE ad_group.id = {ad_group_id} "
        f"AND ad_group_criterion.criterion_id = {criterion_id} "
        "AND ad_group_criterion.type = 'KEYWORD'",
        f"Keyword {criterion_id} was not found in ad group {ad_group_id} of "
        f"customer {customer_id}.",
    )
    criterion = row.ad_group_criterion
    if criterion.negative:
        raise ToolError(
            f"Keyword {criterion_id} is a negative keyword, which has no bid."
        )
    current_bid_micros = (
        criterion.cpc_bid_micros or criterion.effective_cpc_bid_micros
    )
    _check_increase(
        current_bid_micros,
        new_bid_micros,
        MAX_BID_INCREASE_ENV_VAR,
        "max CPC bid",
    )

    operation = _update_operation(
        client,
        "ad_group_criterion",
        criterion.resource_name,
        cpc_bid_micros=new_bid_micros,
    )
    resource_names = _send(
        client, "ad_group_criterion", customer_id, [operation], validate_only
    )
    return _result(
        "set_keyword_cpc_bid",
        customer_id,
        validate_only,
        [
            {
                "resource_name": criterion.resource_name,
                "ad_group": row.ad_group.name,
                "keyword": criterion.keyword.text,
                "match_type": criterion.keyword.match_type.name,
                "currency": row.customer.currency_code,
                "bid_was_inherited_from_ad_group": not criterion.cpc_bid_micros,
                "cpc_bid": {
                    "from": _from_micros(current_bid_micros),
                    "to": _from_micros(new_bid_micros),
                },
            }
        ],
        resource_names,
        _bidding_warnings(row.campaign.bidding_strategy_type),
    )
