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

"""Request quota shared by every connection to the server.

The Google Ads API doesn't report how much of a developer token's daily quota
is left, so the server counts the tool calls it makes itself. Counters live in
shared storage (Firestore or Redis) so the limit applies across all clients and
all server instances; without shared storage they are kept in memory, which is
only correct for a single instance.

Two fixed windows are supported, both aligned to UTC:
  * an hourly limit (GOOGLE_ADS_MCP_QUOTA_HOURLY_LIMIT, 100 by default);
  * a daily budget (GOOGLE_ADS_MCP_QUOTA_DAILY_LIMIT, the developer token's
    daily operations), of which GOOGLE_ADS_MCP_QUOTA_DAILY_RESERVE_PERCENT is
    kept in reserve and never used by the server.
"""

import asyncio
import datetime
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

logger = logging.getLogger(__name__)

_FIRESTORE_COLLECTION = "google_ads_mcp_quota"
_REDIS_KEY_PREFIX = "google_ads_mcp_quota:"


@dataclass(frozen=True)
class Window:
    """A fixed time window with a maximum number of requests."""

    name: str
    limit: int
    seconds: int

    def bucket(self, now: float) -> tuple[str, float]:
        """Returns the storage key and reset time of the window around `now`."""
        start = int(now - now % self.seconds)
        return f"{self.name}-{start}", float(start + self.seconds)


class QuotaBackend:
    """Stores request counters. Implementations must be safe across callers."""

    async def consume(
        self, buckets: list[tuple[str, int, int]]
    ) -> tuple[bool, list[int]]:
        """Counts one request in every bucket, unless one of them is full.

        Args:
            buckets: (key, limit, ttl_seconds) for each window.

        Returns:
            Whether the request was counted, and each bucket's count after the
            call. When a bucket is full nothing is counted.
        """
        raise NotImplementedError


class MemoryQuotaBackend(QuotaBackend):
    """Counters for a single process; not shared between instances."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._counts: dict[str, tuple[int, float]] = {}

    async def consume(self, buckets):
        async with self._lock:
            now = time.time()
            self._counts = {k: v for k, v in self._counts.items() if v[1] > now}
            counts = [self._counts.get(k, (0, 0.0))[0] for k, _, _ in buckets]
            if any(c >= limit for c, (_, limit, _) in zip(counts, buckets)):
                return False, counts
            for (key, _, ttl), count in zip(buckets, counts):
                self._counts[key] = (count + 1, now + ttl)
            return True, [c + 1 for c in counts]


class RedisQuotaBackend(QuotaBackend):
    """Counters in Redis, updated with atomic INCR."""

    def __init__(self, url: str):
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url)

    async def consume(self, buckets):
        keys = [_REDIS_KEY_PREFIX + key for key, _, _ in buckets]
        counts = []
        for key, (_, _, ttl) in zip(keys, buckets):
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, ttl)
            counts.append(count)
        if all(c <= limit for c, (_, limit, _) in zip(counts, buckets)):
            return True, counts
        # Roll back so rejected requests don't use up the quota.
        for key in keys:
            await self._redis.decr(key)
        return False, [c - 1 for c in counts]


class FirestoreQuotaBackend(QuotaBackend):
    """Counters in Firestore, updated in a transaction.

    Each document carries an `expire_at` field; add a Firestore TTL policy on
    it to have old windows deleted automatically.
    """

    def __init__(self, project: str | None, database: str | None):
        from google.cloud import firestore

        self._firestore = firestore
        self._client = firestore.AsyncClient(project=project, database=database)

    async def consume(self, buckets):
        firestore = self._firestore
        collection = self._client.collection(_FIRESTORE_COLLECTION)
        refs = [collection.document(key) for key, _, _ in buckets]

        @firestore.async_transactional
        async def _consume(transaction):
            counts = []
            for ref in refs:
                snapshot = await ref.get(transaction=transaction)
                data = snapshot.to_dict() if snapshot.exists else None
                counts.append((data or {}).get("count", 0))
            if any(c >= limit for c, (_, limit, _) in zip(counts, buckets)):
                return False, counts
            now = datetime.datetime.now(datetime.timezone.utc)
            for ref, count, (_, _, ttl) in zip(refs, counts, buckets):
                transaction.set(
                    ref,
                    {
                        "count": count + 1,
                        "expire_at": now + datetime.timedelta(seconds=ttl),
                    },
                )
            return True, [c + 1 for c in counts]

        return await _consume(self._client.transaction())


def create_quota_backend() -> QuotaBackend:
    """Picks the counter storage, following the OAuth storage settings.

    GOOGLE_ADS_MCP_QUOTA_STORAGE_TYPE overrides the choice. File storage can't
    be updated atomically, so it falls back to memory.
    """
    st_type = os.environ.get("GOOGLE_ADS_MCP_QUOTA_STORAGE_TYPE") or (
        os.environ.get("GOOGLE_ADS_MCP_STORAGE_TYPE")
    )
    r_url = os.environ.get("GOOGLE_ADS_MCP_STORAGE_REDIS_URL")
    fs_project = os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_PROJECT")
    fs_database = os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_DATABASE")

    if not st_type:
        if r_url:
            st_type = "redis"
        elif fs_project or fs_database:
            st_type = "firestore"
        else:
            st_type = "memory"
    st_type = st_type.lower()

    if st_type == "redis":
        return RedisQuotaBackend(r_url or "redis://localhost:6379/0")
    if st_type == "firestore":
        return FirestoreQuotaBackend(fs_project, fs_database)
    if st_type != "memory":
        logger.warning(
            "Quota counters can't use '%s' storage; keeping them in memory.",
            st_type,
        )
    logger.warning(
        "Quota counters are kept in memory, so each server instance has its "
        "own limit. Use firestore or redis storage to share it."
    )
    return MemoryQuotaBackend()


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _format_reset(reset_at: float) -> str:
    return datetime.datetime.fromtimestamp(
        reset_at, datetime.timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


class QuotaMiddleware(Middleware):
    """Limits tool calls across all connections and reports what's left."""

    def __init__(
        self,
        windows: list[Window],
        backend: QuotaBackend,
        warn_percent: int = 20,
    ):
        self._windows = windows
        self._backend = backend
        self._warn_percent = warn_percent

    @classmethod
    def from_env(cls) -> "QuotaMiddleware | None":
        """Builds the middleware from environment variables.

        Returns None when every limit is disabled (set to 0).
        """
        windows = []
        hourly = _get_int_env("GOOGLE_ADS_MCP_QUOTA_HOURLY_LIMIT", 100)
        if hourly > 0:
            windows.append(Window("hour", hourly, 3600))

        daily = _get_int_env("GOOGLE_ADS_MCP_QUOTA_DAILY_LIMIT", 0)
        reserve = _get_int_env("GOOGLE_ADS_MCP_QUOTA_DAILY_RESERVE_PERCENT", 20)
        if daily > 0:
            usable = daily * (100 - reserve) // 100
            windows.append(Window("day", max(usable, 1), 86400))

        if not windows:
            return None
        return cls(
            windows,
            create_quota_backend(),
            warn_percent=_get_int_env("GOOGLE_ADS_MCP_QUOTA_WARN_PERCENT", 20),
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        now = time.time()
        buckets = [w.bucket(now) for w in self._windows]
        try:
            allowed, counts = await self._backend.consume(
                [
                    (key, w.limit, int(reset_at - now) + 60)
                    for w, (key, reset_at) in zip(self._windows, buckets)
                ]
            )
        except Exception:
            # Don't take the server down with the counter storage.
            logger.error("Failed to update the request quota", exc_info=True)
            return await call_next(context)

        if not allowed:
            exhausted = [
                f"limit of {w.limit} requests per {w.name} reached, resets at "
                f"{_format_reset(reset_at)}"
                for w, (_, reset_at), count in zip(
                    self._windows, buckets, counts
                )
                if count >= w.limit
            ]
            raise ToolError(
                "Google Ads API request quota of this MCP server is used up "
                "(shared by all users): "
                + "; ".join(exhausted)
                + ". Tell the user and don't retry before the reset time."
            )

        result = await call_next(context)
        status = self._status(counts, buckets)
        result.content.append(mt.TextContent(type="text", text=status["text"]))
        result.meta = {**(result.meta or {}), "quota": status["windows"]}
        return result

    def _status(
        self, counts: list[int], buckets: list[tuple[str, float]]
    ) -> dict[str, Any]:
        windows = []
        parts = []
        low = False
        for w, count, (_, reset_at) in zip(self._windows, counts, buckets):
            remaining = max(w.limit - count, 0)
            low = low or remaining * 100 <= w.limit * self._warn_percent
            windows.append(
                {
                    "window": w.name,
                    "limit": w.limit,
                    "remaining": remaining,
                    "resets_at": _format_reset(reset_at),
                }
            )
            parts.append(
                f"{remaining}/{w.limit} requests left this {w.name} "
                f"(resets {_format_reset(reset_at)})"
            )
        text = "[quota, shared by all users] " + "; ".join(parts)
        if low:
            text = (
                "WARNING: the request quota is almost used up, tell the user. "
                + text
            )
        return {"text": text, "windows": windows}
