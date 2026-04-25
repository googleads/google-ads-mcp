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

"""Entry point for the MCP server."""

from ads_mcp.coordinator import mcp

# The following imports are necessary to register the tools with the `mcp`
# object, even though they are not directly used in this file.
# The `# noqa: F401` comment tells the linter to ignore the "unused import"
# warning.
from ads_mcp.tools import (  # noqa: F401
    search,
    core,
    get_resource_metadata,
    budgets,
    campaigns,
    ad_groups,
    ads,
    keywords,
    conversions,
    geo,
    keyword_planner,
    assets,
    audiences,
    performance_max,
    bidding_strategies,
    experiments,
    bid_modifiers,
)
from ads_mcp.resources import (
    discovery,
    metrics,
    release_notes,
    segments,
)  # noqa: F401


import os


def run_server() -> None:
    _CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
    _CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")

    if _CLIENT_ID and _CLIENT_SECRET:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    run_server()
