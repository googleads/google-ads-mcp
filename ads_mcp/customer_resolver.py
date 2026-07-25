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

"""Resolves which accounts a user can reach, and how to reach them.

Google Ads access is granted either directly on an account or on a manager
account (MCC), in which case it cascades to every account beneath it. To query
a child account through a manager grant, the API requires a `login-customer-id`
header naming a manager in that child's hierarchy.

This module derives both facts per user, live from the Google Ads hierarchy:

1. `ListAccessibleCustomers` returns the accounts the user is a *direct* member
   of -- under a nested-MCC structure these are the sub-MCCs they were granted.
2. A `customer_client` query rooted at each of those expands it to every
   descendant account, which is what the user actually works on.

Google Ads therefore remains the single source of truth for access; nothing
here is configured server-side.
"""

from __future__ import annotations

import dataclasses
import hashlib
import threading
import time
from typing import Dict, List, Optional

import ads_mcp.utils as utils

# How long a resolved access map is reused before being rebuilt from the API.
_CACHE_TTL_SECONDS = 600

# Deliberately in-memory and per-process. This map is a projection of a user's
# *access control* state, so staleness is a security property, not just a
# freshness one: letting it expire (or vanish when a Cloud Run instance is
# recycled) is what stops a revoked grant from lingering. Rebuilding costs one
# cheap API call per accessible root, so persisting it would buy nothing and
# widen the revocation window.
_cache: Dict[str, "_CacheEntry"] = {}
_cache_lock = threading.Lock()

_CUSTOMER_CLIENT_QUERY = """
    SELECT
      customer_client.id,
      customer_client.descriptive_name,
      customer_client.manager,
      customer_client.level,
      customer_client.status,
      customer_client.currency_code,
      customer_client.time_zone
    FROM customer_client
"""


@dataclasses.dataclass(frozen=True)
class Account:
    """An account the authenticated user can reach."""

    customer_id: str
    descriptive_name: str
    manager: bool
    level: int
    status: str
    currency_code: str
    time_zone: str
    # The manager account to send as `login-customer-id` when querying this
    # account, or None when it is reachable by a direct grant.
    login_customer_id: Optional[str]


@dataclasses.dataclass(frozen=True)
class AccessMap:
    """Everything the authenticated user can reach, and how."""

    # Accounts the user is a direct member of (sub-MCCs, or standalone
    # accounts under a flat grant).
    roots: List[str]
    accounts: Dict[str, Account]

    def login_customer_id_for(self, customer_id: str) -> Optional[str]:
        """Returns the manager to act through for `customer_id`, if any."""
        account = self.accounts.get(_normalize(customer_id))
        return account.login_customer_id if account else None


@dataclasses.dataclass
class _CacheEntry:
    expires_at: float
    access_map: AccessMap


def _normalize(customer_id: str) -> str:
    """Strips punctuation so 123-456-7890 and 1234567890 are the same id."""
    return customer_id.replace("-", "").replace(" ", "").strip()


def _identity() -> str:
    """Returns a stable cache key for the calling user.

    Uses the OAuth subject when the server runs behind the FastMCP OAuth proxy,
    and falls back to hashing the raw token so a key is never shared between
    two users. Under Application Default Credentials (local stdio use) the
    process serves a single user, so a constant key is correct.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
    except Exception:  # not running under an authenticated FastMCP request
        token = None

    if token is None:
        return "adc"

    subject = getattr(token, "subject", None)
    if subject:
        return f"sub:{subject}"

    claims = getattr(token, "claims", None) or {}
    for claim in ("sub", "email"):
        if claims.get(claim):
            return f"{claim}:{claims[claim]}"

    digest = hashlib.sha256(token.token.encode()).hexdigest()
    return f"tok:{digest[:32]}"


def _list_root_customer_ids() -> List[str]:
    """Returns the ids of accounts the user is a direct member of."""
    service = utils.build_googleads_service("CustomerService")
    response = service.list_accessible_customers()
    return [name.removeprefix("customers/") for name in response.resource_names]


def _expand_root(root_customer_id: str) -> List[Account]:
    """Returns every account beneath `root_customer_id`, including itself.

    The query is issued *through* the root, which is what authorizes access to
    its descendants. A non-manager root simply returns itself at level 0, so
    direct account grants need no special handling.
    """
    service = utils.build_googleads_service(
        "GoogleAdsService", login_customer_id=root_customer_id
    )

    accounts: List[Account] = []
    for batch in service.search_stream(
        customer_id=root_customer_id, query=_CUSTOMER_CLIENT_QUERY
    ):
        for row in batch.results:
            client = row.customer_client
            customer_id = str(client.id)
            accounts.append(
                Account(
                    customer_id=customer_id,
                    descriptive_name=client.descriptive_name,
                    manager=client.manager,
                    level=int(client.level),
                    status=client.status.name,
                    currency_code=client.currency_code,
                    time_zone=client.time_zone,
                    # Reaching the root itself needs no manager context; every
                    # descendant is reached by acting through the root.
                    login_customer_id=(
                        None
                        if customer_id == root_customer_id
                        else root_customer_id
                    ),
                )
            )
    return accounts


def _build_access_map() -> AccessMap:
    """Resolves the caller's reachable accounts from the live hierarchy."""
    roots = _list_root_customer_ids()
    accounts: Dict[str, Account] = {}

    for root in roots:
        try:
            expanded = _expand_root(root)
        except Exception as error:
            # One unreadable root (for example a manager the user was removed
            # from mid-session) must not hide every other account they have.
            utils.logger.warning(
                "ads_mcp: could not expand accessible root %s: %s", root, error
            )
            continue

        for account in expanded:
            # First root wins, so an account reachable through two managers
            # resolves deterministically.
            accounts.setdefault(account.customer_id, account)

    utils.logger.info(
        "ads_mcp: resolved %d account(s) under %d accessible root(s)",
        len(accounts),
        len(roots),
    )
    return AccessMap(roots=roots, accounts=accounts)


def get_access_map(force_refresh: bool = False) -> AccessMap:
    """Returns the caller's access map, rebuilding it when the cache is cold."""
    key = _identity()
    now = time.monotonic()

    if not force_refresh:
        with _cache_lock:
            entry = _cache.get(key)
            if entry and entry.expires_at > now:
                return entry.access_map

    access_map = _build_access_map()

    with _cache_lock:
        _cache[key] = _CacheEntry(
            expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
            access_map=access_map,
        )
    return access_map


def resolve_login_customer_id(customer_id: str) -> Optional[str]:
    """Returns the manager to act through when querying `customer_id`.

    Returns None when the account is directly accessible, or when it cannot be
    resolved -- in the latter case the call is still attempted without manager
    context so the Google Ads API reports the authoritative error.
    """
    customer_id = _normalize(customer_id)

    login_customer_id = get_access_map().login_customer_id_for(customer_id)
    if login_customer_id is not None:
        return login_customer_id

    access_map = get_access_map()
    if customer_id in access_map.accounts:
        return None

    # Unknown account: the grant may be newer than the cached map.
    access_map = get_access_map(force_refresh=True)
    return access_map.login_customer_id_for(customer_id)


def clear_cache() -> None:
    """Drops every cached access map. Used by tests."""
    with _cache_lock:
        _cache.clear()
