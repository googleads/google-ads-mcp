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

"""Tools for exposing the API Search method to the MCP server."""

from typing import Any, Dict, List
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


def search(
    customer_id: str,
    fields: List[str],
    resource: str,
    conditions: List[str] = None,
    orderings: List[str] = None,
    limit: int | str = None,
) -> List[Dict[str, Any]]:
    """Fetches data from the Google Ads API using the search method

    Args:
        customer_id: The id of the customer
        fields: The fields to fetch
        resource: The resource to return fields from
        conditions: List of conditions to filter the data, combined using AND clauses
        orderings: How the data is ordered
        limit: The maximum number of rows to return

    """

    ga_service = utils.get_googleads_service("GoogleAdsService")

    query_parts = [f"SELECT {','.join(fields)} FROM {resource}"]

    if conditions:
        query_parts.append(f" WHERE {' AND '.join(conditions)}")

    if orderings:
        query_parts.append(f" ORDER BY {','.join(orderings)}")

    if limit:
        query_parts.append(f" LIMIT {limit}")

    query_parts.append(" PARAMETERS omit_unselected_resource_names=true")

    query = "".join(query_parts)
    utils.logger.info(f"ads_mcp.search query {query}")

    try:
        query_result = ga_service.search_stream(
            customer_id=customer_id, query=query
        )

        final_output: List = []
        for batch in query_result:
            for row in batch.results:
                final_output.append(
                    utils.format_output_row(row, batch.field_mask.paths)
                )
        return final_output
    except GoogleAdsException as ex:
        error_msgs = [
            f"Google Ads API Error: {error.message}"
            for error in ex.failure.errors
        ]
        raise ToolError(
            f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)
        )


def _search_tool_description() -> str:
    """Returns the description for the `search` tool."""
    # Add a warning that will be part of the description
    file_content = (
        "WARNING: The list of valid resources is missing. "
        "Tool may not function correctly."
    )

    try:
        with open(utils.get_gaql_resources_filepath(), "r") as file:
            file_content = file.read()
    except FileNotFoundError:
        utils.logger.error("The specified file was not found.")

    return f"""
{search.__doc__}

## CRITICAL RULES
- **customer_id**: Must be a string of digits ONLY. Remove all hyphens (e.g., use '1234567890', NOT '123-456-7890').
- **Dates**: Must use 'YYYY-MM-DD' format with dashes. Do NOT use date literals (e.g., 'TODAY', 'YESTERDAY'). Always use finite ranges with start and end dates.
- **Fields**: Do NOT guess fields. You MUST use the `get_resource_metadata` tool to discover valid fields for a resource before querying. Always use the full field name (e.g., 'campaign.id').

## Usage Hints
- **Query Grammar**: See https://developers.google.com/google-ads/api/docs/query/grammar for syntax.
- **Resources Overview**: See https://developers.google.com/google-ads/api/fields/v23/overview for all resources.
- **Conversions**: For conversion issues, check `offline_conversion_upload_conversion_action_summary` or see https://developers.google.com/google-ads/api/docs/conversions/upload-summaries.
- **Limits**: Queries to `change_event` must have a `LIMIT` <= 10000.

## Valid Resources
What follows is a list of valid resources that can be queried.
{file_content}
"""


# The `search` tool requires a more complex description that's generated at
# runtime. Uses the `add_tool` method instead of an annnotation since `add_tool`
# provides the flexibility needed to generate the description while also
# including the `search` method's docstring.
search.__doc__ = _search_tool_description()
mcp.add_tool(search)
