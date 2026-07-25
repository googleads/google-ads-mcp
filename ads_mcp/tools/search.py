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

import textwrap
from typing import Any, Dict, List
from fastmcp import FastMCP
from fastmcp.tools import Tool
from mcp.types import ToolAnnotations

search_mcp = FastMCP("search")

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


def search(
    customer_id: str,
    fields: List[str],
    resource: str,
    conditions: List[str] = [],
    orderings: List[str] = [],
    limit: int | None = None,
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

    ga_service = utils.get_googleads_service(
        "GoogleAdsService", customer_id=customer_id
    )

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


def _dedent_docstring(docstring: str) -> str:
    """Removes the body indentation of a docstring, keeping its summary line.

    The generated description below appends unindented sections to this
    docstring. Leaving the original `Args:` block indented would mix
    indentation levels within one docstring, which stops the argument
    descriptions being parsed out into the tool schema at all.
    """
    summary, separator, body = docstring.partition("\n")
    return summary + separator + textwrap.dedent(body)


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
{_dedent_docstring(search.__doc__)}

### Hints
    Language Grammar can be found at https://developers.google.com/google-ads/api/docs/query/grammar
    All resources and descriptions are found at https://developers.google.com/google-ads/api/fields/latest/overview
    If the query fails, a ToolError will be raised with the error details.

    For Conversion issues try looking in offline_conversion_upload_conversion_action_summary

### Hint for customer_id
    should be a string of numbers without punctuation
    if presented in the form 123-456-7890 remove the hyphens and use 1234567890

### Hints for Dates
    All dates should be in the form YYYY-MM-DD and must include the dashes (-)
    Date ranges must be finite and must include a start and end date

### Hints for limits
    Requests to resource change_event must specify a LIMIT of less than or equal to 10000

### Hints for conversions questions
    https://developers.google.com/google-ads/api/docs/conversions/upload-summaries 


### Hints for all resources
    To find out which specific fields (including compatible metrics and segments) you can select, filter by, or sort by for a given resource, you MUST use the `get_resource_metadata` tool.
    Do not guess the fields. Use the tool to look them up.
    Once you have the fields, ensure the whole field name is used (e.g., 'campaign.id', not just 'id'). Wildcards and partial fields are not allowed.

### Valid resources
    What follows is a list of valid resources that can be queried.
    {file_content}
"""


# The `search` tool requires a more complex description that's generated at
# runtime. Uses the `add_tool` method instead of an annnotation since `add_tool`
# provides the flexibility needed to generate the description while also
# including the `search` method's docstring.
search.__doc__ = _search_tool_description()
search_mcp.add_tool(
    Tool.from_function(search, annotations=ToolAnnotations(readOnlyHint=True))
)
