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

from ads_mcp.usage_log import UsageLogMiddleware


import logging
import os

_LOGGERS_THAT_PRINT_ACCESS_TOKENS = ("httpx", "httpx2")


def run_server() -> None:
    for logger_name in _LOGGERS_THAT_PRINT_ACCESS_TOKENS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    _CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
    _CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    port = int(os.environ.get("PORT", "8080"))

    if _CLIENT_ID and _CLIENT_SECRET:
        # Usage logging stays mandatory in hosted mode, but the middleware is
        # attached here rather than in coordinator.py so that importing the
        # coordinator does not require MCP_USAGE_DSN. A missing DSN still
        # raises, before the server accepts any traffic.
        mcp.add_middleware(UsageLogMiddleware.from_env(server="google-ads"))
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
