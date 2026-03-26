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

"""Release notes resource."""

import urllib.request

from ads_mcp.coordinator import mcp


@mcp.resource(
    uri="resource://release-notes",
    mime_type="text/html",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def get_release_notes() -> str:
    """Retrieve the Google Ads API release notes.

    Provides the official release notes for the Google Ads API, detailing new
    features, changes, deprecations, and bug fixes across all API versions.
    Host LLMs should access this resource to check for breaking changes,
    determine if a specific feature is supported in a given API version, or
    troubleshoot issues by consulting recent API updates.

    Returns:
        str: The release notes in HTML format.
    """
    url = "https://developers.google.com/google-ads/api/docs/release-notes"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")
