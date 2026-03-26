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

"""Tools for fetching metadata for Google Ads resources."""

from typing import Dict, List, Any
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_resource_metadata(resource_name: str) -> Dict[str, Any]:
    """Retrieves the selectable, filterable, and sortable fields for a specific Google Ads resource.

    Use this tool to find out which fields you can select, filter by, or sort by
    when querying a specific resource (e.g., 'campaign', 'ad_group').
    Do not guess fields, you MUST use this tool to discover them.

    The responses of this tool should be cached, as they don't change frequently.

    Args:
        resource_name: The name of the Google Ads resource (e.g., 'campaign', 'ad_group').
    """
    ga_service = utils.get_googleads_service("GoogleAdsFieldService")
    request = utils.get_googleads_type("SearchGoogleAdsFieldsRequest")

    # The Google Ads Field Service supports LIKE operator natively.
    # This filter ensures we only get rows that belong to the queried resource.
    query = f"SELECT name, selectable, filterable, sortable WHERE name LIKE '{resource_name}.%'"
    request.query = query

    try:
        response = ga_service.search_google_ads_fields(request=request)
    except Exception as e:
        utils.logger.info(
            f"Failed query with LIKE: {e}. Falling back to fetching all fields."
        )
        # Fallback to fetching all fields if the API doesn't support the query or syntax
        query = "SELECT name, selectable, filterable, sortable"
        request.query = query
        try:
            response = ga_service.search_google_ads_fields(request=request)
        except Exception as e2:
            raise RuntimeError(
                f"API call to search_google_ads_fields failed: {e2}"
            )

    selectable = []
    filterable = []
    sortable = []

    for googleads_field in response:
        field_name = googleads_field.name

        # We only care about fields belonging to this resource
        # Since field names are of the format "campaign.id", "campaign.name", etc.,
        # this check guarantees exactly that.
        if field_name.startswith(f"{resource_name}."):
            if googleads_field.selectable:
                selectable.append(field_name)
            if googleads_field.filterable:
                filterable.append(field_name)
            if googleads_field.sortable:
                sortable.append(field_name)

    return {
        "resource": resource_name,
        "selectable": sorted(selectable),
        "filterable": sorted(filterable),
        "sortable": sorted(sortable),
    }
