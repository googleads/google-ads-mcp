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

"""Tests for conditional write tool registration."""

import os
import subprocess
import sys
import unittest


class TestWriteRegistration(unittest.TestCase):
    """Test cases for conditional write tool registration."""

    def _list_tool_names(self, env: dict) -> list[str]:
        """Returns sorted MCP tool names for a subprocess with the given env."""
        script = """
import asyncio
from ads_mcp.tools import search, core, get_resource_metadata  # noqa: F401
from ads_mcp.tools import write_registration
write_registration.register_write_tools()
from ads_mcp.coordinator import mcp

async def main():
    tools = await mcp.list_tools()
    print(",".join(sorted(t.name for t in tools)))

asyncio.run(main())
"""
        merged = {**os.environ, **env}
        merged.setdefault("GOOGLE_ADS_DEVELOPER_TOKEN", "test-token")
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=merged,
            cwd=os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout,
        )
        return result.stdout.strip().split(",")

    def test_default_tools_only(self):
        """Tests that only read tools are registered by default."""
        names = self._list_tool_names(
            {
                "GOOGLE_ADS_MCP_ENABLE_MUTATE": "",
                "GOOGLE_ADS_MCP_ENABLE_REMOVE": "",
            }
        )
        self.assertEqual(
            names,
            [
                "get_resource_metadata",
                "list_accessible_customers",
                "search",
            ],
        )

    def test_mutate_tools_registered(self):
        """Tests that create and update are registered when mutate is enabled."""
        names = self._list_tool_names({"GOOGLE_ADS_MCP_ENABLE_MUTATE": "1"})
        self.assertIn("create", names)
        self.assertIn("update", names)
        self.assertNotIn("remove", names)

    def test_remove_tool_registered(self):
        """Tests that remove is registered when remove env is enabled."""
        names = self._list_tool_names(
            {
                "GOOGLE_ADS_MCP_ENABLE_MUTATE": "1",
                "GOOGLE_ADS_MCP_ENABLE_REMOVE": "1",
            }
        )
        self.assertIn("remove", names)
