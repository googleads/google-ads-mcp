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

# The following imports are necessary to register the resources with the `mcp`
# object, even though they are not directly used in this file.
# Tools are loaded dynamically via reflection in coordinator.py.
# The `# noqa: F401` comment tells the linter to ignore the "unused import"
# warning.
from ads_mcp.resources import (
    discovery,
    metrics,
    release_notes,
    segments,
)  # noqa: F401


import os

import ads_mcp.utils as utils


def _log_startup_diagnostics() -> None:
    """Logs what this process is actually running.

    A deployment serving a stale image is otherwise near-impossible to spot:
    the code in the repository and the code answering requests disagree with
    no visible symptom. Printing the resolved dependency versions and the
    mounted tool names makes that mismatch obvious in the deploy log.
    """
    import asyncio
    from importlib.metadata import PackageNotFoundError, version

    def _version(package: str) -> str:
        try:
            return version(package)
        except PackageNotFoundError:
            return "not installed"

    utils.logger.info(
        "ads_mcp startup: fastmcp=%s google-ads=%s",
        _version("fastmcp"),
        _version("google-ads"),
    )

    try:
        tools = asyncio.run(mcp.list_tools())
        names = sorted(tool.name for tool in tools)
    except Exception as e:  # diagnostics must never block startup
        utils.logger.warning(
            "ads_mcp startup: could not enumerate tools (%s)", e
        )
        return

    utils.logger.info(
        "ads_mcp startup: %d tools mounted: %s", len(names), ", ".join(names)
    )
    utils.logger.info(
        "ads_mcp startup: mutations %s",
        "ENABLED" if any("mutate" in name for name in names) else "disabled",
    )


def run_server() -> None:
    _CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
    _CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    port = int(os.environ.get("PORT", "8080"))

    _log_startup_diagnostics()

    if _CLIENT_ID and _CLIENT_SECRET:
        mcp.run(
            transport="streamable-http",
            port=port,
            host="0.0.0.0",
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run()


if __name__ == "__main__":
    run_server()
