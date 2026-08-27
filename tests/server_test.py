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

"""Test cases for the server module."""

import logging
import unittest
from unittest.mock import patch


class TestUtils(unittest.TestCase):
    """Test cases for the server module."""

    def test_server_initialization(self):
        """Tests that the MCP server instance is initialized.

        This servers as a smoke test to confirm there are no obvious issues
        with initialization, such as missing imports.
        """
        from ads_mcp import server

        self.assertIsNotNone(server.mcp, "MCP server instance not initialized")

    def test_oauth_server_uses_stateful_streamable_http(self):
        """OAuth mode supports modern and legacy Streamable HTTP clients."""
        from ads_mcp import server

        env = {
            "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID": "test-client",
            "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET": "test-secret",
            "PORT": "18080",
        }
        with patch.dict(server.os.environ, env, clear=True):
            with patch.object(server.mcp, "run") as run:
                server.run_server()

        run.assert_called_once_with(
            transport="streamable-http",
            port=18080,
            host="0.0.0.0",
            uvicorn_config={"access_log": False},
        )

    def test_http_client_info_logs_are_suppressed(self):
        """OAuth tokeninfo URLs must not be emitted at INFO level."""
        from ads_mcp import server

        logger = logging.getLogger("httpx2")
        previous_level = logger.level
        try:
            logger.setLevel(logging.NOTSET)
            server.configure_safe_http_logging()
            self.assertEqual(logging.WARNING, logger.level)
        finally:
            logger.setLevel(previous_level)

    def test_server_without_oauth_uses_stdio(self):
        """Local credential mode retains FastMCP's default stdio transport."""
        from ads_mcp import server

        with patch.dict(server.os.environ, {}, clear=True):
            with patch.object(server.mcp, "run") as run:
                server.run_server()

        run.assert_called_once_with()
