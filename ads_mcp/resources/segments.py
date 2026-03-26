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

"""Segments resource."""

import urllib.request

from ads_mcp.coordinator import mcp


@mcp.resource(
    uri="resource://segments",
    mime_type="text/html",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def get_segments() -> str:
    """Retrieve the Google Ads API segments documentation.

    Provides the official documentation for segments in the Google Ads API,
    detailing the available segments that can be used in GAQL queries to
    partition metrics.
    Host LLMs should access this resource to understand which segments
    can be used with specific resources and metrics.

    Returns:
        str: The segments documentation in HTML format.
    """
    url = "https://developers.google.com/google-ads/api/fields/latest/segments"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")
