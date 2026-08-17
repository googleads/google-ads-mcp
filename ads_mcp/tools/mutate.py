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

"""Tools for exposing the API Mutate method to the MCP server.

Unlike the other tool namespaces, these tools write to the customer's account.
They are namespaced separately so that deployments can disable them wholesale
via `tools_config.yaml`.
"""

from typing import Any, Dict, List
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

mutate_mcp = FastMCP("mutate")

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from google.api_core import protobuf_helpers
from fastmcp.exceptions import ToolError

# Mirrors ResponseContentTypeEnum. RESOURCE_NAME_ONLY keeps responses small,
# which matters because a batch can contain thousands of operations.
_RESPONSE_CONTENT_TYPES = ("RESOURCE_NAME_ONLY", "MUTABLE_RESOURCE")


def _normalize_customer_id(customer_id: str) -> str:
    """Returns the customer id with the conventional hyphens removed."""
    return customer_id.replace("-", "").replace(" ", "")


def _ensure_update_mask(operation) -> None:
    """Fills in `update_mask` for update operations that omit one.

    The API silently ignores every field absent from `update_mask`, so an
    update without a mask is a no-op rather than an error. Deriving the mask
    from the fields actually set on the resource is what the Google Ads client
    examples do, and it avoids a class of confusing silent failures.
    """
    pb = operation._pb
    op_field = pb.WhichOneof("operation")
    if op_field is None:
        raise ToolError(
            "Each entry in `operations` must set exactly one operation field, "
            "for example 'campaign_operation' or 'ad_group_operation'."
        )

    sub_pb = getattr(operation, op_field)._pb
    field_names = {field.name for field in sub_pb.DESCRIPTOR.fields}

    if "update" not in field_names or "update_mask" not in field_names:
        return
    if not sub_pb.HasField("update"):
        return
    if sub_pb.update_mask.paths:
        return

    sub_pb.update_mask.CopyFrom(
        protobuf_helpers.field_mask(None, sub_pb.update)
    )


def _build_operations(client, operations: List[Dict[str, Any]]) -> List[Any]:
    """Converts the incoming dicts into MutateOperation protos."""
    if not operations:
        raise ToolError("`operations` must contain at least one operation.")

    operation_cls = type(client.get_type("MutateOperation"))

    built = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ToolError(
                f"operations[{index}] must be an object, got "
                f"{type(operation).__name__}."
            )
        try:
            proto_operation = operation_cls(operation)
        except Exception as e:
            raise ToolError(
                f"operations[{index}] is not a valid operation: {e}"
            )

        _ensure_update_mask(proto_operation)
        built.append(proto_operation)

    return built


def _format_results(response, include_resource: bool) -> List[Dict[str, Any]]:
    """Summarizes each operation response, newest API fields included."""
    results = []
    for operation_response in response.mutate_operation_responses:
        result_field = operation_response._pb.WhichOneof("response")
        if result_field is None:
            results.append({})
            continue

        result = getattr(operation_response, result_field)
        entry: Dict[str, Any] = {
            "operation": result_field,
            "resource_name": getattr(result, "resource_name", ""),
        }
        if include_resource:
            entry["resource"] = utils.format_output_value(result)
        results.append(entry)

    return results


def _describe_failure(ex: GoogleAdsException) -> str:
    """Renders a GoogleAdsException, keeping the failing operation index."""
    messages = []
    for error in ex.failure.errors:
        location = ""
        field_path = [
            element.field_name
            for element in error.location.field_path_elements
            if element.field_name
        ]
        if field_path:
            location = f" (at {'.'.join(field_path)})"
        messages.append(f"Google Ads API Error: {error.message}{location}")

    return f"Request ID: {ex.request_id}\n" + "\n".join(messages)


@mutate_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
    )
)
def mutate(
    customer_id: str,
    operations: List[Dict[str, Any]],
    validate_only: bool = True,
    partial_failure: bool = False,
    response_content_type: str = "RESOURCE_NAME_ONLY",
) -> Dict[str, Any]:
    """Creates, updates, or removes Google Ads resources.

    This tool WRITES to the account. It wraps GoogleAdsService.Mutate, so a
    single call can mix operations across resource types and they are applied
    atomically: either all of them succeed or none of them do.

    Args:
        customer_id: The id of the customer to mutate. Digits only.
        operations: A list of MutateOperation objects. Each entry sets exactly
            one operation field, which in turn sets one of create/update/remove.
        validate_only: When true (the default) the request is validated and
            then discarded WITHOUT applying anything. Call again with
            validate_only=false to actually apply the changes.
        partial_failure: When true, valid operations are applied and failed
            ones are reported in `partial_failure_error` instead of failing the
            whole batch. Cannot be combined with validate_only.
        response_content_type: "RESOURCE_NAME_ONLY" (default) or
            "MUTABLE_RESOURCE" to return the full resource after mutation.

    Returns:
        A dict with `applied` (whether anything was actually written),
        `results` (one entry per operation) and `partial_failure_error`.

    ### Workflow
        ALWAYS call this once with validate_only=true first, show the user what
        would change, and only call again with validate_only=false once the
        user has confirmed. Never pass validate_only=false on the first call.

    ### Shape of each operation
        {"campaign_budget_operation": {"create": {...}}}
        {"campaign_operation": {"update": {...}}}
        {"ad_group_operation": {"remove": "customers/123/adGroups/456"}}

        `remove` takes a resource name string. `create` and `update` take an
        object. Use the `get_resource_metadata` tool to look up the fields on a
        resource. Do not guess field names.

    ### Creating dependent resources in one call
        A resource created in this batch can be referenced by later operations
        using a temporary resource name with a NEGATIVE id. Each temporary id
        must be unique within the request. For example, to create a budget and
        a campaign that uses it:

        [
          {"campaign_budget_operation": {"create": {
              "resource_name": "customers/1234567890/campaignBudgets/-1",
              "name": "Example budget",
              "amount_micros": 20000000,
              "delivery_method": "STANDARD"}}},
          {"campaign_operation": {"create": {
              "name": "Example campaign",
              "status": "PAUSED",
              "advertising_channel_type": "SEARCH",
              "campaign_budget": "customers/1234567890/campaignBudgets/-1",
              "manual_cpc": {}}}}
        ]

    ### Hints for updates
        Updates need a `resource_name` identifying what to change plus the
        fields to change. `update_mask` is derived automatically from the
        fields you set, so send only the fields you actually want changed.

    ### Hints for money
        Monetary fields are in micros: multiply the currency amount by
        1,000,000. A $20.00 daily budget is 20000000 amount_micros.

    ### Hints for customer_id
        Digits only, no punctuation. Given 123-456-7890, use 1234567890.

    ### Hints for safety
        Prefer creating campaigns with status "PAUSED" so the user can review
        them before they start spending money.
    """
    if validate_only and partial_failure:
        raise ToolError(
            "partial_failure cannot be used with validate_only. Set "
            "partial_failure=false to preview, or validate_only=false to apply."
        )

    if response_content_type not in _RESPONSE_CONTENT_TYPES:
        raise ToolError(
            f"response_content_type must be one of "
            f"{', '.join(_RESPONSE_CONTENT_TYPES)}."
        )

    customer_id = _normalize_customer_id(customer_id)
    client = utils.get_googleads_client()
    built_operations = _build_operations(client, operations)

    request = client.get_type("MutateGoogleAdsRequest")
    request.customer_id = customer_id
    request.mutate_operations = built_operations
    request.validate_only = validate_only
    request.partial_failure = partial_failure
    request.response_content_type = response_content_type

    utils.logger.info(
        "ads_mcp.mutate customer_id=%s operations=%d validate_only=%s",
        customer_id,
        len(built_operations),
        validate_only,
    )

    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.mutate(request=request)
    except GoogleAdsException as ex:
        raise ToolError(_describe_failure(ex))

    partial_failure_error = None
    if response._pb.HasField("partial_failure_error"):
        partial_failure_error = utils.format_output_value(
            response.partial_failure_error
        )

    return {
        "applied": not validate_only,
        "validate_only": validate_only,
        "customer_id": customer_id,
        "operation_count": len(built_operations),
        "results": _format_results(
            response, response_content_type == "MUTABLE_RESOURCE"
        ),
        "partial_failure_error": partial_failure_error,
        "message": (
            "DRY RUN: the request was validated but NOTHING was changed. "
            "Show these results to the user, and call again with "
            "validate_only=false to apply them."
            if validate_only
            else "Changes were applied to the account."
        ),
    }
