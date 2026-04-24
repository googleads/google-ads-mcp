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

from typing import Any, Dict
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_resource_metadata(resource_name: str) -> Dict[str, Any]:
    """Retrieves the selectable, filterable, and sortable fields for a specific Google Ads resource,
    including compatible metrics and segments.

    Use this tool to find out which fields you can select, filter by, or sort by
    when querying a specific resource (e.g., 'campaign', 'ad_group').
    This tool also returns metrics and segments that can be selected with the resource.
    Their names start with 'metrics.' and 'segments.' respectively.

    Do not guess fields, you MUST use this tool to discover them before constructing a query for the
    `search` tool.

    The responses of this tool should be cached, as they don't change frequently.

    Args:
        resource_name: The name of the Google Ads resource (e.g., 'campaign', 'ad_group').
    """
    ga_service = utils.get_googleads_service("GoogleAdsFieldService")
    request = utils.get_googleads_type("SearchGoogleAdsFieldsRequest")

    selectable = set()
    filterable = set()
    sortable = set()

    # Query 1: Get resource attributes
    attributes_query = f"SELECT name, selectable, filterable, sortable WHERE name LIKE '{resource_name}.%' AND category = 'ATTRIBUTE'"
    request.query = attributes_query
    try:
        attributes_response = ga_service.search_google_ads_fields(
            request=request
        )
        for field in attributes_response:
            if field.selectable:
                selectable.add(field.name)
            if field.filterable:
                filterable.add(field.name)
            if field.sortable:
                sortable.add(field.name)
    except Exception as e:
        utils.logger.warning(f"Failed attributes query: {e}")
        # Fallback to original behavior if category filter fails
        fallback_query = f"SELECT name, selectable, filterable, sortable WHERE name LIKE '{resource_name}.%'"
        request.query = fallback_query
        try:
            attributes_response = ga_service.search_google_ads_fields(
                request=request
            )
            for field in attributes_response:
                if field.name.startswith(f"{resource_name}."):
                    if field.selectable:
                        selectable.add(field.name)
                    if field.filterable:
                        filterable.add(field.name)
                    if field.sortable:
                        sortable.add(field.name)
        except Exception as e2:
            utils.logger.error(f"Fallback attributes query failed: {e2}")
            raise RuntimeError(
                f"API call to search_google_ads_fields failed: {e2}"
            )

    # Query 2: Get selectable metrics and segments
    metrics_segments_query = f"SELECT name, selectable, filterable, sortable WHERE selectable_with CONTAINS ANY('{resource_name}')"
    request.query = metrics_segments_query
    try:
        metrics_segments_response = ga_service.search_google_ads_fields(
            request=request
        )
        for field in metrics_segments_response:
            if field.selectable:
                selectable.add(field.name)
            if field.filterable:
                filterable.add(field.name)
            if field.sortable:
                sortable.add(field.name)
    except Exception as e:
        utils.logger.warning(f"Failed metrics/segments query: {e}")

    return {
        "resource": resource_name,
        "selectable": sorted(list(selectable)),
        "filterable": sorted(list(filterable)),
        "sortable": sorted(list(sortable)),
    }
