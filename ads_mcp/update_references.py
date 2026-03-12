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

"""Tools for generating file containing a list of resources and their fields."""

import collections
import functools
import json
import os
import typing
from collections.abc import Callable

from google.ads.googleads.v22.services.services.google_ads_field_service import (
    GoogleAdsFieldServiceClient,
)
from google.ads.googleads.v22.services.types.google_ads_field_service import (
    SearchGoogleAdsFieldsRequest,
)
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

import ads_mcp.utils as utils

T = typing.TypeVar("T")
P = typing.ParamSpec("P")


def set_auth_context(fn: Callable[P, T]) -> Callable[P, T]:
    """Sets the auth context for the MCP server using service account credentials."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        GADS_ACCESS_TOKEN = os.getenv("GADS_ACCESS_TOKEN")
        if GADS_ACCESS_TOKEN:
            at = AccessToken(
                token=GADS_ACCESS_TOKEN,
                client_id="",
                scopes=[],
                expires_at=0,
                resource=None,
            )
            auth_context_var.set(AuthenticatedUser(at))
        return fn(*args, **kwargs)

    return wrapper


@set_auth_context
def update_gaql_resource_file() -> None:
    """Fetches all Google Ads fields and their attributes, groups them by resource, and saves to a JSON file."""

    ga_service: GoogleAdsFieldServiceClient = utils.get_googleads_service(
        "GoogleAdsFieldService"
    )

    request: SearchGoogleAdsFieldsRequest = utils.get_googleads_type(
        "SearchGoogleAdsFieldsRequest"
    )
    # Query to select the name and key attributes for ALL fields.
    # We no longer filter by category = 'RESOURCE' here, as we need attributes
    # for all fields associated with resources.
    query = "SELECT name, selectable, filterable, sortable"
    request.query = query

    try:
        response = ga_service.search_google_ads_fields(request=request)
    except Exception as e:
        raise RuntimeError(f"API call to search_google_ads_fields failed: {e}")

    if response.total_results_count == 0:
        print("No GoogleAdsFields found.")
        return

    # Dictionary to store the grouped results
    # Example: {'campaign': {'selectable': [], 'filterable': [], 'sortable': []}, ...}
    resource_data = collections.defaultdict(
        lambda: {"selectable": [], "filterable": [], "sortable": []}
    )  # type: ignore[var-annotated]

    for googleads_field in response:
        field_name = googleads_field.name
        # Extract the base resource name (e.g., 'campaign' from 'campaign.id')
        if "." in field_name:
            resource_name = field_name.split(".")[0]

            if googleads_field.selectable:
                resource_data[resource_name]["selectable"].append(field_name)
            if googleads_field.filterable:
                resource_data[resource_name]["filterable"].append(field_name)
            if googleads_field.sortable:
                resource_data[resource_name]["sortable"].append(field_name)
        # We can ignore fields that don't contain a '.' as they are likely
        # top-level resources themselves and don't have these attributes in the same way.

    # Prepare the final output structure
    output_list = []
    for resource, attributes in resource_data.items():
        output_list.append(
            {
                "resource": resource,
                "selectable": sorted(attributes["selectable"]),
                "filterable": sorted(attributes["filterable"]),
                "sortable": sorted(attributes["sortable"]),
            }
        )

    # Sort the list of resources for consistent output
    output_list.sort(key=lambda x: x["resource"])

    file_path = utils.get_gaql_resources_filepath()

    try:
        with open(file_path, "w") as file:
            json.dump(output_list, file, indent=4)
        print(f"Successfully updated resource file: {file_path}")
    except OSError as e:
        raise RuntimeError(f"Failed to write to file {file_path}: {e}")


if __name__ == "__main__":
    update_gaql_resource_file()
