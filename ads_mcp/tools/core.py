# Copyright 2025 Google LLC.
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

import json
from ads_mcp.coordinator import mcp

import ads_mcp.utils as utils

from google.ads.googleads.v21.services.types.customer_service import (
    ListAccessibleCustomersResponse,
)


@mcp.tool()
def list_accessible_customers() -> str:
    """Returns ids of customers directly accessible by the user authenticating the call."""
    ga_service = utils.get_googleads_service("CustomerService")
    accessible_customers: ListAccessibleCustomersResponse = (
        ga_service.list_accessible_customers()
    )
    # remove customer/ from the start of each resource
    customer_ids = [
        cust_rn.removeprefix("customers/")
        for cust_rn in accessible_customers.resource_names
    ]
    return json.dumps({"customer_ids": customer_ids, "count": len(customer_ids)}, indent=2)
