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

"""Unit tests for the shared request quota."""

import asyncio
import os
import unittest
from unittest.mock import patch

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ads_mcp.quota import (
    MemoryQuotaBackend,
    QuotaMiddleware,
    Window,
)


def _make_server(windows, warn_percent=20):
    server = FastMCP("test")

    @server.tool
    def ping() -> str:
        return "pong"

    server.add_middleware(
        QuotaMiddleware(windows, MemoryQuotaBackend(), warn_percent)
    )
    return server


async def _call(server, times):
    texts = []
    async with Client(server) as client:
        for _ in range(times):
            result = await client.call_tool("ping")
            texts.append([c.text for c in result.content])
    return texts


class TestQuotaMiddleware(unittest.TestCase):
    """Tests counting, blocking and reporting of the quota."""

    def test_reports_remaining_requests(self):
        server = _make_server([Window("hour", 10, 3600)])
        texts = asyncio.run(_call(server, 2))
        self.assertEqual(texts[0][0], "pong")
        self.assertIn("9/10 requests left this hour", texts[0][1])
        self.assertIn("8/10 requests left this hour", texts[1][1])
        self.assertNotIn("WARNING", texts[1][1])

    def test_warns_when_quota_is_low(self):
        server = _make_server([Window("hour", 5, 3600)], warn_percent=20)
        texts = asyncio.run(_call(server, 4))
        self.assertNotIn("WARNING", texts[2][1])
        self.assertTrue(texts[3][1].startswith("WARNING"))

    def test_blocks_when_quota_is_used_up(self):
        server = _make_server([Window("hour", 2, 3600)])
        asyncio.run(_call(server, 2))
        with self.assertRaisesRegex(ToolError, "limit of 2 requests per hour"):
            asyncio.run(_call(server, 1))

    def test_rejected_requests_are_not_counted(self):
        backend = MemoryQuotaBackend()
        buckets = [("hour-0", 1, 3600), ("day-0", 5, 86400)]
        self.assertEqual(asyncio.run(backend.consume(buckets)), (True, [1, 1]))
        self.assertEqual(asyncio.run(backend.consume(buckets)), (False, [1, 1]))

    def test_window_buckets_align_to_window(self):
        window = Window("hour", 1, 3600)
        self.assertEqual(window.bucket(7300.0), ("hour-7200", 10800.0))


class TestQuotaFromEnv(unittest.TestCase):
    """Tests building the middleware from environment variables."""

    def test_default_is_100_per_hour(self):
        with patch.dict(os.environ, {}, clear=True):
            middleware = QuotaMiddleware.from_env()
        self.assertEqual(middleware._windows, [Window("hour", 100, 3600)])

    def test_daily_limit_keeps_reserve(self):
        env = {
            "GOOGLE_ADS_MCP_QUOTA_HOURLY_LIMIT": "0",
            "GOOGLE_ADS_MCP_QUOTA_DAILY_LIMIT": "15000",
        }
        with patch.dict(os.environ, env, clear=True):
            middleware = QuotaMiddleware.from_env()
        self.assertEqual(middleware._windows, [Window("day", 12000, 86400)])

    def test_disabled_when_all_limits_are_zero(self):
        env = {"GOOGLE_ADS_MCP_QUOTA_HOURLY_LIMIT": "0"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(QuotaMiddleware.from_env())


if __name__ == "__main__":
    unittest.main()
