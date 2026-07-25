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

"""Test cases for resolving a user's accessible accounts."""

import threading
import unittest
from unittest.mock import MagicMock, patch

from ads_mcp import customer_resolver


def _customer_client_row(
    customer_id, name="Account", manager=False, level=1, status="ENABLED"
):
    """Builds a stand-in for a `customer_client` result row."""
    row = MagicMock()
    row.customer_client.id = int(customer_id)
    row.customer_client.descriptive_name = name
    row.customer_client.manager = manager
    row.customer_client.level = level
    row.customer_client.status.name = status
    row.customer_client.currency_code = "EUR"
    row.customer_client.time_zone = "Europe/Istanbul"
    return row


def _batch(rows):
    batch = MagicMock()
    batch.results = rows
    return batch


class CustomerResolverTest(unittest.TestCase):
    """Test cases for `ads_mcp.customer_resolver`."""

    def setUp(self):
        customer_resolver.clear_cache()
        self.addCleanup(customer_resolver.clear_cache)

    def _mock_services(self, roots, expansions):
        """Returns a `build_googleads_service` stand-in.

        Args:
            roots: Customer ids `ListAccessibleCustomers` should return.
            expansions: Maps a root id to the rows its `customer_client`
                query yields, or to an exception to raise.
        """
        customer_service = MagicMock()
        customer_service.list_accessible_customers.return_value.resource_names = [
            f"customers/{root}" for root in roots
        ]

        def build(service_name, login_customer_id=None):
            if service_name == "CustomerService":
                return customer_service

            expansion = expansions[login_customer_id]
            ads_service = MagicMock()
            if isinstance(expansion, Exception):
                ads_service.search_stream.side_effect = expansion
            else:
                ads_service.search_stream.return_value = [_batch(expansion)]
            return ads_service

        return build

    def test_expands_sub_mcc_to_its_child_accounts(self):
        """A manager grant resolves to every account beneath it."""
        build = self._mock_services(
            roots=["100"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "Sub MCC", manager=True, level=0
                    ),
                    _customer_client_row("201", "Client A"),
                    _customer_client_row("202", "Client B"),
                ]
            },
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            access_map = customer_resolver.get_access_map()

        self.assertEqual(access_map.roots, ["100"])
        self.assertEqual(sorted(access_map.accounts), ["100", "201", "202"])
        # Children are reached by acting through the sub-MCC...
        self.assertEqual(access_map.login_customer_id_for("201"), "100")
        self.assertEqual(access_map.login_customer_id_for("202"), "100")
        # ...while the granted account itself needs no manager context.
        self.assertIsNone(access_map.login_customer_id_for("100"))

    def test_direct_account_grant_needs_no_manager(self):
        """A leaf grant returns just itself, with no login-customer-id."""
        build = self._mock_services(
            roots=["555"],
            expansions={"555": [_customer_client_row("555", "Smore", level=0)]},
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            access_map = customer_resolver.get_access_map()

        self.assertEqual(sorted(access_map.accounts), ["555"])
        self.assertIsNone(access_map.login_customer_id_for("555"))

    def test_customer_id_punctuation_is_ignored(self):
        """Ids formatted as 123-456-7890 resolve like their bare form."""
        build = self._mock_services(
            roots=["100"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "Sub MCC", manager=True, level=0
                    ),
                    _customer_client_row("2014567890", "Client A"),
                ]
            },
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            resolved = customer_resolver.resolve_login_customer_id(
                "201-456-7890"
            )

        self.assertEqual(resolved, "100")

    def test_unreadable_root_does_not_hide_other_accounts(self):
        """Losing access to one manager keeps the remaining ones usable."""
        build = self._mock_services(
            roots=["100", "300"],
            expansions={
                "100": RuntimeError("PERMISSION_DENIED"),
                "300": [
                    _customer_client_row(
                        "300", "Other MCC", manager=True, level=0
                    ),
                    _customer_client_row("301", "Client C"),
                ],
            },
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            access_map = customer_resolver.get_access_map()

        self.assertEqual(sorted(access_map.accounts), ["300", "301"])
        self.assertEqual(access_map.login_customer_id_for("301"), "300")

    def test_account_under_two_managers_resolves_deterministically(self):
        """An overlapping account always resolves through the first root."""
        shared = _customer_client_row("900", "Shared Client")
        build = self._mock_services(
            roots=["100", "300"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "MCC One", manager=True, level=0
                    ),
                    shared,
                ],
                "300": [
                    _customer_client_row(
                        "300", "MCC Two", manager=True, level=0
                    ),
                    shared,
                ],
            },
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            access_map = customer_resolver.get_access_map()

        self.assertEqual(access_map.login_customer_id_for("900"), "100")

    def test_access_map_is_cached_between_calls(self):
        """A warm cache serves later calls without re-querying the API."""
        build = MagicMock(
            side_effect=self._mock_services(
                roots=["100"],
                expansions={
                    "100": [
                        _customer_client_row(
                            "100", "Sub MCC", manager=True, level=0
                        ),
                        _customer_client_row("201", "Client A"),
                    ]
                },
            )
        )

        with patch("ads_mcp.utils.build_googleads_service", build):
            customer_resolver.get_access_map()
            call_count = build.call_count
            customer_resolver.get_access_map()

        self.assertEqual(build.call_count, call_count)

    def test_expired_cache_is_rebuilt(self):
        """A stale map is refetched so revoked access stops working."""
        build = MagicMock(
            side_effect=self._mock_services(
                roots=["100"],
                expansions={
                    "100": [
                        _customer_client_row(
                            "100", "Sub MCC", manager=True, level=0
                        )
                    ]
                },
            )
        )

        with patch("ads_mcp.utils.build_googleads_service", build):
            customer_resolver.get_access_map()
            call_count = build.call_count
            with (
                patch("ads_mcp.customer_resolver._CACHE_TTL_SECONDS", -1),
                patch.dict(customer_resolver._cache, {}, clear=True),
            ):
                customer_resolver.get_access_map()

        self.assertGreater(build.call_count, call_count)

    def test_unknown_account_is_attempted_without_manager(self):
        """An unresolvable id falls through to the API for the real error."""
        build = self._mock_services(
            roots=["100"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "Sub MCC", manager=True, level=0
                    )
                ]
            },
        )

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            resolved = customer_resolver.resolve_login_customer_id("999")

        self.assertIsNone(resolved)

    def test_cache_is_isolated_between_users(self):
        """One user's accounts are never served to a different user."""
        alice = self._mock_services(
            roots=["100"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "Alice MCC", manager=True, level=0
                    ),
                    _customer_client_row("201", "Alice Client"),
                ]
            },
        )
        bob = self._mock_services(
            roots=["300"],
            expansions={
                "300": [
                    _customer_client_row(
                        "300", "Bob MCC", manager=True, level=0
                    ),
                    _customer_client_row("301", "Bob Client"),
                ]
            },
        )

        def resolve_as(identity, build):
            with (
                patch(
                    "ads_mcp.customer_resolver._identity", return_value=identity
                ),
                patch(
                    "ads_mcp.utils.build_googleads_service", side_effect=build
                ),
            ):
                return customer_resolver.get_access_map()

        alice_map = resolve_as("sub:alice", alice)
        bob_map = resolve_as("sub:bob", bob)

        self.assertEqual(sorted(alice_map.accounts), ["100", "201"])
        self.assertEqual(sorted(bob_map.accounts), ["300", "301"])
        self.assertNotIn("301", alice_map.accounts)
        self.assertNotIn("201", bob_map.accounts)

        # Alice's cached map must still be hers after Bob has been resolved.
        with patch(
            "ads_mcp.customer_resolver._identity", return_value="sub:alice"
        ):
            self.assertEqual(
                sorted(customer_resolver.get_access_map().accounts),
                ["100", "201"],
            )

    def test_identity_differs_per_access_token(self):
        """Distinct callers never share a cache key."""

        def identity_for(subject=None, claims=None, token="raw-token"):
            access_token = MagicMock()
            access_token.subject = subject
            access_token.claims = claims
            access_token.token = token
            with patch(
                "fastmcp.server.dependencies.get_access_token",
                return_value=access_token,
            ):
                return customer_resolver._identity()

        self.assertNotEqual(
            identity_for(subject="alice"), identity_for(subject="bob")
        )
        # Falls back to claims, then to hashing the raw token.
        self.assertEqual(
            identity_for(claims={"email": "a@example.com"}),
            "email:a@example.com",
        )
        self.assertNotEqual(
            identity_for(token="token-a"), identity_for(token="token-b")
        )

    def test_concurrent_callers_get_a_consistent_map(self):
        """The cache stays coherent when requests overlap."""
        build = self._mock_services(
            roots=["100"],
            expansions={
                "100": [
                    _customer_client_row(
                        "100", "Sub MCC", manager=True, level=0
                    ),
                    _customer_client_row("201", "Client A"),
                ]
            },
        )

        results = []
        errors = []

        def worker():
            try:
                results.append(
                    sorted(customer_resolver.get_access_map().accounts)
                )
            except Exception as error:  # pragma: no cover - failure path
                errors.append(error)

        with patch("ads_mcp.utils.build_googleads_service", side_effect=build):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(results, [["100", "201"]] * 8)


if __name__ == "__main__":
    unittest.main()
