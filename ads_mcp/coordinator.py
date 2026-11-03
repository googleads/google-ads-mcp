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

"""Module declaring the singleton MCP instance.

The singleton allows other modules to register their tools with the same MCP
server using `@mcp.tool` annotations, thereby 'coordinating' the bootstrapping
of the server.
"""

import logging
import os
from typing import Any
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from ads_mcp.auth_storage import create_client_storage
from ads_mcp.quota import QuotaMiddleware

logger = logging.getLogger(__name__)

_CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
_CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
_BASE_URL = os.environ.get("GOOGLE_ADS_MCP_BASE_URL", "http://localhost:8080")
_JWT_SIGNING_KEY = os.environ.get("GOOGLE_ADS_MCP_JWT_SIGNING_KEY")

# Lifetime of the access token FastMCP hands to MCP clients. By default
# FastMCP mirrors Google's 1 hour lifetime, and many MCP clients don't use the
# refresh token, so users had to reconnect every hour. The FastMCP token is a
# reference token: the server re-validates the Google token on every request
# and refreshes it with the stored Google refresh token, so a longer lifetime
# doesn't extend access beyond what Google allows.
_DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 30 * 24 * 3600
# Refresh the Google token this many seconds before it expires, so a request
# never runs with a token that expires mid-flight.
_TOKEN_EXPIRY_THRESHOLD_SECONDS = 60


def _get_access_token_ttl() -> int:
    value = os.environ.get("GOOGLE_ADS_MCP_ACCESS_TOKEN_TTL_SECONDS")
    return int(value) if value else _DEFAULT_ACCESS_TOKEN_TTL_SECONDS


def _warn_if_storage_is_ephemeral(client_storage: Any) -> None:
    """Warns when OAuth state won't survive a restart or reach other instances.

    Without shared storage the mapping from a client's token to the user's
    Google tokens lives on the instance's local disk. On Cloud Run that disk is
    lost whenever an instance is replaced or scaled to zero, and isn't shared
    between instances, so clients get a 401 and must log in again.
    """
    st_type = (os.environ.get("GOOGLE_ADS_MCP_STORAGE_TYPE") or "").lower()
    if client_storage is not None and st_type not in ("memory", "filetree"):
        return
    logger.warning(
        "OAuth tokens are stored on the local instance (%s). Users will have "
        "to log in again after every restart or scale event, and whenever a "
        "request reaches another instance. Set GOOGLE_ADS_MCP_STORAGE_TYPE to "
        "'firestore' or 'redis' for deployments such as Cloud Run.",
        st_type or "default file store",
    )


if _CLIENT_ID and _CLIENT_SECRET:
    client_storage = create_client_storage()
    _warn_if_storage_is_ephemeral(client_storage)
    provider_kwargs: dict[str, Any] = {
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "base_url": _BASE_URL,
        "required_scopes": [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/adwords",
        ],
        "fastmcp_access_token_expiry_seconds": _get_access_token_ttl(),
        "token_expiry_threshold_seconds": _TOKEN_EXPIRY_THRESHOLD_SECONDS,
    }
    if _JWT_SIGNING_KEY:
        provider_kwargs["jwt_signing_key"] = _JWT_SIGNING_KEY
    if client_storage is not None:
        provider_kwargs["client_storage"] = client_storage

    auth = GoogleProvider(**provider_kwargs)
    mcp = FastMCP("Google Ads Server", auth=auth)
else:
    mcp = FastMCP("Google Ads Server")

_quota_middleware = QuotaMiddleware.from_env()
if _quota_middleware is not None:
    mcp.add_middleware(_quota_middleware)


def initialize_and_mount_tools(parent_mcp: FastMCP) -> None:
    """Loads the tools configuration and dynamically mounts the tools sub-servers."""
    from ads_mcp.config import ToolsConfig
    import importlib
    import pkgutil
    import ads_mcp.tools as tools_pkg

    # Map of category name -> FastMCP sub-server
    sub_servers = {}

    # Discover and dynamically load all tool modules
    for _, module_name, _ in pkgutil.iter_modules(tools_pkg.__path__):
        full_module_name = f"ads_mcp.tools.{module_name}"
        module = importlib.import_module(full_module_name)

        # Find any FastMCP instances defined in the module
        for attr_name in dir(module):
            attr_val = getattr(module, attr_name)
            if isinstance(attr_val, FastMCP):
                category = attr_val.name
                sub_servers[category] = attr_val

    config = ToolsConfig.load()

    for category, sub_mcp in sub_servers.items():
        if not config.is_namespace_enabled(category):
            continue

        # Filter disabled tools inside the sub-server before mounting
        tool_names = []
        for key, val in sub_mcp.local_provider._components.items():
            if key.startswith("tool:"):
                tool_names.append(val.name)

        for name in tool_names:
            if not config.is_tool_enabled(category, name):
                sub_mcp.local_provider.remove_tool(name)

        # Determine prefix/namespace
        namespace_prefix = config.get_namespace_prefix(category)

        # Mount the sub-server
        parent_mcp.mount(sub_mcp, namespace=namespace_prefix or None)


# Automatically initialize and mount tools upon import
initialize_and_mount_tools(mcp)
