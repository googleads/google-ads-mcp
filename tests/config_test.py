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

"""Test cases for the config module."""

import unittest
from unittest.mock import patch, mock_open
from ads_mcp.config import ToolsConfig


class TestToolsConfig(unittest.TestCase):
    """Test cases for ToolsConfig parser."""

    def test_default_config_exposes_all_with_default_namespaces(self):
        """Tests that if no config is supplied, all default namespaces are enabled."""
        config = ToolsConfig()
        self.assertTrue(config.is_namespace_enabled("customers"))
        self.assertTrue(config.is_namespace_enabled("search"))
        self.assertTrue(config.is_namespace_enabled("metadata"))
        self.assertTrue(config.is_namespace_enabled("labels"))
        self.assertTrue(config.is_namespace_enabled("assets"))
        self.assertFalse(config.is_namespace_enabled("unknown_category"))

        self.assertEqual(config.get_namespace_prefix("customers"), "customers")
        self.assertEqual(config.get_namespace_prefix("search"), "search")
        self.assertEqual(config.get_namespace_prefix("labels"), "labels")
        self.assertEqual(config.get_namespace_prefix("assets"), "assets")

        self.assertTrue(config.is_tool_enabled("search", "search"))
        self.assertTrue(config.is_tool_enabled("assets", "create_asset"))
        self.assertTrue(config.is_tool_enabled("labels", "manage_labels"))

    def test_boolean_namespaces(self):
        """Tests namespaces enabled via simple booleans."""
        data = {
            "namespaces": {
                "customers": True,
                "search": False,
            }
        }
        config = ToolsConfig(data)
        self.assertTrue(config.is_namespace_enabled("customers"))
        self.assertFalse(config.is_namespace_enabled("search"))
        # Not listed => False by default if namespaces dict is present
        self.assertFalse(config.is_namespace_enabled("metadata"))

        self.assertEqual(config.get_namespace_prefix("customers"), "customers")
        self.assertTrue(
            config.is_tool_enabled("customers", "list_accessible_customers")
        )
        self.assertFalse(config.is_tool_enabled("search", "search"))

    def test_custom_namespace_prefixes(self):
        """Tests namespaces configured with custom prefix strings."""
        data = {
            "namespaces": {
                "customers": "accounts",
                "search": "query_engine",
            }
        }
        config = ToolsConfig(data)
        self.assertTrue(config.is_namespace_enabled("customers"))
        self.assertTrue(config.is_namespace_enabled("search"))

        self.assertEqual(config.get_namespace_prefix("customers"), "accounts")
        self.assertEqual(config.get_namespace_prefix("search"), "query_engine")

    def test_fine_grained_tool_enablement(self):
        """Tests selectively enabling/disabling specific tools under a namespace."""
        data = {
            "namespaces": {
                "customers": {
                    "enabled": True,
                    "prefix": "users",
                    "enabled_tools": [
                        {"list_accessible_customers": True},
                        {"another_tool": False},
                    ],
                },
                "search": {
                    "enabled": True,
                    # No prefix specified, defaults to category name
                    "enabled_tools": ["search"],
                },
            }
        }
        config = ToolsConfig(data)
        self.assertTrue(config.is_namespace_enabled("customers"))
        self.assertTrue(config.is_namespace_enabled("search"))

        self.assertEqual(config.get_namespace_prefix("customers"), "users")
        self.assertEqual(config.get_namespace_prefix("search"), "search")

        self.assertTrue(
            config.is_tool_enabled("customers", "list_accessible_customers")
        )
        self.assertFalse(config.is_tool_enabled("customers", "another_tool"))
        self.assertFalse(config.is_tool_enabled("customers", "unlisted_tool"))

        self.assertTrue(config.is_tool_enabled("search", "search"))
        self.assertFalse(
            config.is_tool_enabled("search", "unlisted_search_tool")
        )

    @patch("os.path.exists")
    def test_load_missing_file_raises_file_not_found(self, mock_exists):
        """Tests that load raises FileNotFoundError if the config file does not exist."""
        mock_exists.return_value = False
        with self.assertRaises(FileNotFoundError):
            ToolsConfig.load("missing.yaml")

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="invalid-yaml: {")
    def test_load_invalid_file_raises_value_error(self, mock_file, mock_exists):
        """Tests that load raises ValueError if the config file contains invalid YAML."""
        mock_exists.return_value = True
        with self.assertRaises(ValueError):
            ToolsConfig.load("invalid.yaml")

    @patch.dict("os.environ", {"GOOGLE_ADS_MCP_TOOLS_CONFIG": "/env/path.yaml"})
    @patch("os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="namespaces:\n  customers: true\n",
    )
    def test_load_uses_env_var_path(self, mock_file, mock_exists):
        """Tests that the env var is honored when no explicit path is given."""
        config = ToolsConfig.load()
        mock_file.assert_called_once_with("/env/path.yaml", "r")
        self.assertTrue(config.is_namespace_enabled("customers"))

    @patch.dict(
        "os.environ", {"GOOGLE_ADS_MCP_TOOLS_CONFIG": "/env/missing.yaml"}
    )
    @patch("os.path.exists", return_value=False)
    def test_load_missing_env_var_path_raises(self, mock_exists):
        """Tests that a missing env-var-specified config raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            ToolsConfig.load()

    @patch.dict("os.environ", {}, clear=True)
    @patch("os.path.exists", return_value=False)
    @patch("ads_mcp.config.importlib.resources.files")
    def test_load_falls_back_to_bundled_default(self, mock_files, mock_exists):
        """Tests fallback to the package-bundled config when no local file exists."""
        bundled = mock_files.return_value.joinpath.return_value
        bundled.is_file.return_value = True
        bundled.__str__ = lambda self: "/bundled/tools_config.yaml"
        with patch(
            "builtins.open",
            new_callable=mock_open,
            read_data="namespaces:\n  search: true\n",
        ) as mock_file:
            config = ToolsConfig.load()
        mock_file.assert_called_once_with("/bundled/tools_config.yaml", "r")
        self.assertTrue(config.is_namespace_enabled("search"))

    @patch.dict("os.environ", {}, clear=True)
    @patch("os.path.exists", return_value=False)
    @patch("ads_mcp.config.importlib.resources.files")
    def test_load_without_any_config_enables_defaults(
        self, mock_files, mock_exists
    ):
        """Tests that load falls back to all default namespaces if nothing resolves."""
        mock_files.return_value.joinpath.return_value.is_file.return_value = (
            False
        )
        config = ToolsConfig.load()
        self.assertTrue(config.is_namespace_enabled("customers"))
        self.assertTrue(config.is_namespace_enabled("search"))
        self.assertTrue(config.is_namespace_enabled("metadata"))
