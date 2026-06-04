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

"""Tools for exposing Google Ads mutate update operations to the MCP server."""

from typing import Any, Dict, List

from ads_mcp.coordinator import mcp
from ads_mcp.tools import mutate_core
from fastmcp.tools import Tool


def update(
    customer_id: str,
    operations: List[Dict[str, Any]],
    validate_only: bool = False,
    partial_failure: bool = True,
) -> Dict[str, Any]:
    """Updates Google Ads resources using MutateOperation update clauses.

    Each operation must use a nested *Operation message with update and
    updateMask fields, such as campaignOperation.update.

    Args:
        customer_id: The Google Ads customer ID.
        operations: A list of MutateOperation objects in API JSON form.
        validate_only: If True, validates the request without applying changes.
        partial_failure: If True, allows successful operations when some fail.

    Returns:
        A dict of mutate results from GoogleAdsService.mutate.

    Raises:
        ToolError: If the request is invalid or the API returns an error.
    """
    return mutate_core.execute_mutate(
        customer_id=customer_id,
        operations=operations,
        validate_only=validate_only,
        partial_failure=partial_failure,
    )


def _update_tool_description() -> str:
    """Returns the description for the `update` tool."""
    return f"""
{update.__doc__}
{mutate_core._mutate_operations_hints()}
"""


update.__doc__ = _update_tool_description()
mcp.add_tool(Tool.from_function(update))
