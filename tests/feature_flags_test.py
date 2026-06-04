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

"""Tests for environment-gated feature flags."""

import os
import unittest
from unittest import mock

from ads_mcp import feature_flags


class TestFeatureFlags(unittest.TestCase):
    """Test cases for environment-gated feature flags."""

    def test_mutate_disabled_by_default(self):
        """Tests that mutate is disabled when the env variable is unset."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_ADS_MCP_ENABLE_MUTATE", None)
            self.assertFalse(feature_flags.is_mutate_enabled())

    def test_mutate_enabled(self):
        """Tests that mutate is enabled for a truthy env value."""
        with mock.patch.dict(
            os.environ, {"GOOGLE_ADS_MCP_ENABLE_MUTATE": "1"}, clear=True
        ):
            self.assertTrue(feature_flags.is_mutate_enabled())

    def test_remove_requires_mutate(self):
        """Tests that remove stays disabled when mutate is not enabled."""
        with mock.patch.dict(
            os.environ, {"GOOGLE_ADS_MCP_ENABLE_REMOVE": "1"}, clear=True
        ):
            self.assertFalse(feature_flags.is_remove_enabled())

    def test_remove_enabled_with_mutate(self):
        """Tests that remove is enabled when both env flags are truthy."""
        with mock.patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_ENABLE_MUTATE": "true",
                "GOOGLE_ADS_MCP_ENABLE_REMOVE": "yes",
            },
            clear=True,
        ):
            self.assertTrue(feature_flags.is_remove_enabled())

    def test_mutate_chunk_size_default(self):
        """Tests the default mutate chunk size when the env variable is unset."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE", None)
            self.assertEqual(feature_flags.mutate_chunk_size(), 500)

    def test_mutate_chunk_size_invalid(self):
        """Tests that an invalid chunk size env value raises ValueError."""
        with mock.patch.dict(
            os.environ, {"GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE": "nope"}, clear=True
        ):
            with self.assertRaises(ValueError):
                feature_flags.mutate_chunk_size()
