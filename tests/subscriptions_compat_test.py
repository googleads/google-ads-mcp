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

"""Regression tests for MCP 2026 subscription-stream compatibility."""

import unittest

from fastmcp import FastMCP
from mcp import types as mcp_types

from ads_mcp.coordinator import ensure_subscriptions_listen


class SubscriptionsListenCompatibilityTest(unittest.TestCase):
    def test_registers_missing_subscriptions_listen_handler(self):
        server = FastMCP("compat-test")

        self.assertNotIn(
            "subscriptions/listen", server._mcp_server._request_handlers
        )
        self.assertTrue(ensure_subscriptions_listen(server))
        self.assertIn(
            "subscriptions/listen", server._mcp_server._request_handlers
        )

        capabilities = server._mcp_server.get_capabilities(
            protocol_version="2026-07-28"
        )
        self.assertTrue(capabilities.tools.list_changed)

    def test_preserves_native_subscriptions_listen_handler(self):
        server = FastMCP("native-test")

        async def native_handler(context, params):
            del context, params
            return mcp_types.SubscriptionsListenResult()

        server._mcp_server.add_request_handler(
            "subscriptions/listen",
            mcp_types.SubscriptionsListenRequestParams,
            native_handler,
        )
        original_entry = server._mcp_server._request_handlers[
            "subscriptions/listen"
        ]

        self.assertFalse(ensure_subscriptions_listen(server))
        self.assertIs(
            original_entry,
            server._mcp_server._request_handlers["subscriptions/listen"],
        )


if __name__ == "__main__":
    unittest.main()
