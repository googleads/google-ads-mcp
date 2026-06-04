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

"""Shared GoogleAdsService.mutate execution for write MCP tools."""

from typing import Any, Dict, List

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import json_format

import ads_mcp.feature_flags as feature_flags
import ads_mcp.utils as utils


def _normalize_customer_id(customer_id: str) -> str:
    """Strips hyphens and whitespace from a customer ID string.

    Args:
        customer_id: The customer ID, optionally formatted with hyphens.

    Returns:
        The customer ID containing digits only.
    """
    return customer_id.replace("-", "").strip()


def _parse_operations(
    operation_dicts: List[Dict[str, Any]],
) -> List[Any]:
    """Builds MutateOperation protos from REST-style JSON dicts.

    Args:
        operation_dicts: A list of MutateOperation objects using camelCase keys
            as in the Google Ads API REST reference.

    Returns:
        A list of MutateOperation proto-plus messages.

    Raises:
        ToolError: If an entry is not a dict or cannot be parsed as protobuf
            JSON.
    """
    operations = []
    for index, op_dict in enumerate(operation_dicts):
        if not isinstance(op_dict, dict):
            raise ToolError(
                f"Operation at index {index} must be an object, got "
                f"{type(op_dict).__name__}."
            )
        mutate_operation = utils.get_googleads_type("MutateOperation")
        try:
            json_format.ParseDict(
                op_dict,
                mutate_operation._pb,
                ignore_unknown_fields=False,
            )
        except json_format.ParseError as ex:
            raise ToolError(
                f"Invalid MutateOperation at index {index}: {ex}"
            ) from ex
        operations.append(mutate_operation)
    return operations


def _raise_google_ads_exception(ex: GoogleAdsException) -> None:
    """Raises a ToolError that includes the Google Ads API error details.

    Args:
        ex: The GoogleAdsException raised by the API client.

    Raises:
        ToolError: Always raised with the request ID and error messages.
    """
    error_msgs = [
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    ]
    raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))


def execute_mutate(
    customer_id: str,
    operations: List[Dict[str, Any]],
    validate_only: bool = False,
    partial_failure: bool = True,
) -> Dict[str, Any]:
    """Executes GoogleAdsService.mutate with server-side chunking.

    Args:
        customer_id: The Google Ads customer ID.
        operations: MutateOperation payloads in API JSON form (camelCase).
        validate_only: If True, validates the request without applying changes.
        partial_failure: If True, allows successful operations when some fail.

    Returns:
        A dict with key mutate_operation_responses. Includes
        partial_failure_error when the API reports partial failures.

    Raises:
        ToolError: If operations is empty, parsing fails, or the API returns an
            error.
    """
    if not operations:
        raise ToolError("At least one MutateOperation is required.")

    customer_id = _normalize_customer_id(customer_id)
    parsed = _parse_operations(operations)
    chunk_size = feature_flags.mutate_chunk_size()
    ga_service = utils.get_googleads_service("GoogleAdsService")
    request = utils.get_googleads_type("MutateGoogleAdsRequest")
    request.customer_id = customer_id
    request.validate_only = validate_only
    request.partial_failure = partial_failure

    aggregated_responses: List[Any] = []
    last_partial_failure: Any = None

    for start in range(0, len(parsed), chunk_size):
        chunk = parsed[start : start + chunk_size]
        del request.mutate_operations[:]
        request.mutate_operations.extend(chunk)
        utils.logger.info(
            "ads_mcp.mutate customer_id=%s validate_only=%s "
            "partial_failure=%s operations=%s",
            customer_id,
            validate_only,
            partial_failure,
            len(chunk),
        )
        try:
            response = ga_service.mutate(request=request)
        except GoogleAdsException as ex:
            _raise_google_ads_exception(ex)

        aggregated_responses.extend(
            [
                utils.format_output_value(r)
                for r in response.mutate_operation_responses
            ]
        )
        if response.partial_failure_error:
            last_partial_failure = response.partial_failure_error

    result: Dict[str, Any] = {
        "mutate_operation_responses": aggregated_responses,
    }
    if last_partial_failure:
        result["partial_failure_error"] = utils.format_output_value(
            last_partial_failure
        )
    return result


def _mutate_operations_hints() -> str:
    """Returns hint text appended to write tool descriptions."""
    return """
### Hints for operations
    Each item is one MutateOperation in Google Ads API JSON form (camelCase):
    https://developers.google.com/google-ads/api/rest/reference/rest/latest/MutateOperation

    Examples:
    - Update: {"campaignOperation": {"update": {"resourceName": "...", "status": "PAUSED"}, "updateMask": "status"}}
    - Create: {"campaignOperation": {"create": {...}}}
    - Remove: {"campaignOperation": {"remove": "customers/.../campaigns/..."}}

    Use get_resource_metadata before updates. Prefer validate_only=true to dry-run.

### Hint for customer_id
    Should be a string of numbers without punctuation.
    If presented as 123-456-7890, use 1234567890.
"""
