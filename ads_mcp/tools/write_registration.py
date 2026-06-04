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

"""Registers opt-in write tools when enabled via environment variables."""

import ads_mcp.feature_flags as feature_flags
import ads_mcp.utils as utils


def register_write_tools() -> None:
    """Registers write MCP tools when enabled by environment variables.

    Imports create and update when GOOGLE_ADS_MCP_ENABLE_MUTATE is truthy.
    Imports remove when GOOGLE_ADS_MCP_ENABLE_REMOVE is also truthy. Tools are
    not listed in tools/list when their flags are unset.
    """
    if not feature_flags.is_mutate_enabled():
        return

    utils.logger.info(
        "GOOGLE_ADS_MCP_ENABLE_MUTATE is set; registering create and update "
        "tools."
    )
    from ads_mcp.tools import create, update  # noqa: F401

    if feature_flags.is_remove_enabled():
        utils.logger.info(
            "GOOGLE_ADS_MCP_ENABLE_REMOVE is set; registering remove tool."
        )
        from ads_mcp.tools import remove  # noqa: F401
