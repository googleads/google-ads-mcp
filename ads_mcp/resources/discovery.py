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

"""Discovery document resource."""

import urllib.request

from ads_mcp.coordinator import mcp


@mcp.resource(
    uri="resource://discovery-document",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def get_discovery_document() -> str:
    """Retrieve the Google Ads API discovery document.

    Provides the discovery document for the Google Ads API v23, which
    describes the API surface, including resources, methods, and
    schemas.
    Host LLMs should access this resource to understand the structure of
    the Google Ads API and discover available features.

    Returns:
        str: The discovery document in JSON format.
    """
    url = "https://googleads.googleapis.com/$discovery/rest?version=v23"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")
