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

"""Unit tests for authentication configuration and storage setup."""

import os
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch

from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper

try:
    from key_value.aio.stores.redis import RedisStore

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    RedisStore = None

from ads_mcp.auth_storage import create_client_storage


class TestAuthConfig(unittest.TestCase):
    """Tests create_client_storage and auth environment variable configurations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(
            lambda: shutil.rmtree(self.temp_dir, ignore_errors=True)
        )

        # Clear relevant env vars
        self.env_keys = [
            "GOOGLE_ADS_MCP_STORAGE_TYPE",
            "GOOGLE_ADS_MCP_STORAGE_PATH",
            "GOOGLE_ADS_MCP_STORAGE_REDIS_URL",
            "GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY",
            "GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION",
            "GOOGLE_ADS_MCP_JWT_SIGNING_KEY",
            "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID",
            "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET",
            "GOOGLE_ADS_MCP_BASE_URL",
        ]
        self.orig_env = {}
        for key in self.env_keys:
            if key in os.environ:
                self.orig_env[key] = os.environ.pop(key)

    def tearDown(self):
        for key in self.env_keys:
            os.environ.pop(key, None)
        for key, val in self.orig_env.items():
            os.environ[key] = val

    def test_create_client_storage_default_returns_none(self):
        """When no storage env vars or arguments are provided, returns None."""
        self.assertIsNone(create_client_storage())

    def test_create_client_storage_memory(self):
        """Tests creating a memory store."""
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "memory"
        os.environ["GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"] = "test_secret"
        store = create_client_storage()
        self.assertIsInstance(store, FernetEncryptionWrapper)
        self.assertIsInstance(store.key_value, MemoryStore)

    def test_create_client_storage_filetree_with_path(self):
        """Tests creating a filetree store with explicit path."""
        path = os.path.join(self.temp_dir, "filetree_storage")
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "filetree"
        os.environ["GOOGLE_ADS_MCP_STORAGE_PATH"] = path
        os.environ["GOOGLE_ADS_MCP_JWT_SIGNING_KEY"] = "my_jwt_key_123456"
        store = create_client_storage()
        self.assertIsInstance(store, FernetEncryptionWrapper)
        self.assertIsInstance(store.key_value, FileTreeStore)
        self.assertTrue(os.path.exists(path))

    def test_create_client_storage_filetree_env_var(self):
        """Tests creating a filetree store via environment variables."""
        path = os.path.join(self.temp_dir, "filetree_env")
        os.environ["GOOGLE_ADS_MCP_STORAGE_PATH"] = path
        os.environ["GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"] = "sec"
        store = create_client_storage()
        self.assertIsInstance(store, FernetEncryptionWrapper)
        self.assertIsInstance(store.key_value, FileTreeStore)

    def test_create_client_storage_filetree_missing_path_raises(self):
        """Tests that filetree storage without a path raises ValueError."""
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "filetree"
        with self.assertRaises(ValueError):
            create_client_storage()

    @unittest.skipUnless(HAS_REDIS, "redis package not installed")
    def test_create_client_storage_redis(self):
        """Tests creating a redis store."""
        os.environ["GOOGLE_ADS_MCP_STORAGE_REDIS_URL"] = (
            "redis://localhost:6379/1"
        )
        os.environ["GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION"] = "true"
        store = create_client_storage()
        self.assertIsInstance(store, RedisStore)

    def test_create_client_storage_disable_encryption(self):
        """Tests disabling encryption wrapper."""
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "memory"
        os.environ["GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION"] = "true"
        store = create_client_storage()
        self.assertIsInstance(store, MemoryStore)

    def test_create_client_storage_unsupported_type_raises(self):
        """Tests that unsupported storage type raises ValueError."""
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "invalid_type"
        with self.assertRaises(ValueError):
            create_client_storage()

    @patch("fastmcp.server.auth.providers.google.GoogleProvider")
    def test_coordinator_init_with_jwt_signing_key_and_storage(
        self, mock_provider
    ):
        """Tests initializing coordinator when auth env vars are provided."""
        os.environ["GOOGLE_ADS_MCP_OAUTH_CLIENT_ID"] = "dummy_client_id"
        os.environ["GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"] = "dummy_client_secret"
        os.environ["GOOGLE_ADS_MCP_JWT_SIGNING_KEY"] = "custom_jwt_signing_key"
        os.environ["GOOGLE_ADS_MCP_STORAGE_TYPE"] = "memory"

        # Re-import or re-evaluate coordinator logic block
        import importlib
        import ads_mcp.coordinator as coord

        importlib.reload(coord)

        mock_provider.assert_called_once()
        _, kwargs = mock_provider.call_args
        self.assertEqual(kwargs["client_id"], "dummy_client_id")
        self.assertEqual(kwargs["client_secret"], "dummy_client_secret")
        self.assertEqual(kwargs["jwt_signing_key"], "custom_jwt_signing_key")
        self.assertIn("client_storage", kwargs)
        self.assertIsInstance(kwargs["client_storage"], FernetEncryptionWrapper)


if __name__ == "__main__":
    unittest.main()
