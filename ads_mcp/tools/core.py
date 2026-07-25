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

"""Tools for exposing simple, core API methods to the MCP server."""

from typing import Any, Dict, List
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ads_mcp import customer_resolver

customers_mcp = FastMCP("customers")


@customers_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_accessible_customers(
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    """Returns the Google Ads accounts the authenticating user can work in.

    Use this tool first to discover available customer IDs if the user hasn't
    provided one. Most other tools require a valid customer ID as input.

    Access granted on a manager account (MCC) cascades to every account beneath
    it, so this expands each manager the user was granted and returns the
    accounts underneath, not just the manager itself.

    Args:
        include_inactive: Also return accounts that are not enabled (for
            example cancelled or suspended ones). Defaults to False.

    Returns:
        One entry per account, each with:
            customer_id: The id to pass to other tools.
            descriptive_name: The account name shown in the Google Ads UI.
            manager: True for manager accounts (MCCs). These group other
                accounts and hold no campaign data of their own, so query the
                non-manager accounts beneath them instead.
            level: Depth below the granted account; 0 is the granted account.
            status: For example ENABLED, CANCELED, SUSPENDED, CLOSED.
            currency_code: The account's currency, for reading cost metrics.
            time_zone: The account's time zone, which its dates are reported in.
    """
    access_map = customer_resolver.get_access_map()

    accounts = sorted(
        access_map.accounts.values(),
        key=lambda account: (account.level, account.descriptive_name),
    )

    return [
        {
            "customer_id": account.customer_id,
            "descriptive_name": account.descriptive_name,
            "manager": account.manager,
            "level": account.level,
            "status": account.status,
            "currency_code": account.currency_code,
            "time_zone": account.time_zone,
        }
        for account in accounts
        if include_inactive or account.status == "ENABLED"
    ]
