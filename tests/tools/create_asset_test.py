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

"""Test cases for the create_asset tool."""

import base64
import unittest
from unittest.mock import MagicMock, patch, mock_open

from ads_mcp.tools import create_asset


class TestCreateAsset(unittest.IsolatedAsyncioTestCase):
    """Test cases for the create asset tool."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_asset_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_asset_service

        self.mock_asset_op = MagicMock()
        self.mock_asset = MagicMock()
        self.mock_asset_op.create = self.mock_asset

        self.mock_asset_type_enum = MagicMock()
        self.mock_asset_type_enum.AssetType.TEXT = "TEXT"
        self.mock_asset_type_enum.AssetType.IMAGE = "IMAGE"
        self.mock_asset_type_enum.AssetType.YOUTUBE_VIDEO = "YOUTUBE_VIDEO"
        self.mock_asset_type_enum.AssetType.SITELINK = "SITELINK"
        self.mock_asset_type_enum.AssetType.CALLOUT = "CALLOUT"
        self.mock_asset_type_enum.AssetType.STRUCTURED_SNIPPET = "STRUCTURED_SNIPPET"

        self.mock_mime_enum = MagicMock()
        self.mock_mime_enum.MimeType.IMAGE_PNG = "IMAGE_PNG"
        self.mock_mime_enum.MimeType.IMAGE_JPEG = "IMAGE_JPEG"
        self.mock_mime_enum.MimeType.IMAGE_GIF = "IMAGE_GIF"

        def get_type_mock(type_name):
            if type_name == "AssetOperation":
                return self.mock_asset_op
            elif type_name == "AssetTypeEnum":
                return self.mock_asset_type_enum
            elif type_name == "MimeTypeEnum":
                return self.mock_mime_enum
            return MagicMock()

        self.mock_client.get_type.side_effect = get_type_mock

        # Setup default successful response
        self.mock_response = MagicMock()
        mock_result = MagicMock()
        mock_result.resource_name = "customers/123/assets/456"
        self.mock_response.results = [mock_result]
        self.mock_asset_service.mutate_assets.return_value = self.mock_response

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_text_asset(self, mock_get_client):
        """Tests that TEXT asset is created with correct parameters."""
        mock_get_client.return_value = self.mock_client

        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="TEXT",
            name="My Text Asset",
            text_asset_text="Sign up today!",
        )

        self.assertEqual(self.mock_asset.name, "My Text Asset")
        self.assertEqual(self.mock_asset.text_asset.text, "Sign up today!")
        self.mock_asset_service.mutate_assets.assert_called_once()
        self.assertIn("Successfully created asset", result)
        self.assertIn("ID: 456", result)

    @patch("ads_mcp.utils.get_googleads_client")
    @patch("os.path.isfile")
    async def test_create_image_asset_local(self, mock_isfile, mock_get_client):
        """Tests creating an IMAGE asset from a local file path."""
        mock_isfile.return_value = True
        mock_get_client.return_value = self.mock_client

        m = mock_open(read_data=b"fakeimagebytes")
        with patch("builtins.open", m):
            result = await create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                name="My Local Image",
                image_asset_path="/path/to/logo.png",
            )

        self.assertEqual(self.mock_asset.image_asset.data, b"fakeimagebytes")
        self.assertEqual(self.mock_asset.image_asset.mime_type, "IMAGE_PNG")
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_image_asset_base64(self, mock_get_client):
        """Tests creating an IMAGE asset using base64 encoded data."""
        mock_get_client.return_value = self.mock_client
        b64_data = base64.b64encode(b"fakeb64bytes").decode("utf-8")

        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="IMAGE",
            name="My Base64 Image",
            image_asset_data=b64_data,
            image_asset_mime_type="IMAGE_JPEG",
        )

        self.assertEqual(self.mock_asset.image_asset.data, b"fakeb64bytes")
        self.assertEqual(self.mock_asset.image_asset.mime_type, "IMAGE_JPEG")
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_sitelink_asset(self, mock_get_client):
        """Tests creating a SITELINK asset with descriptions and final URLs."""
        mock_get_client.return_value = self.mock_client

        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="SITELINK",
            name="Contact Us Sitelink",
            sitelink_link_text="Contact Us",
            sitelink_description1="Get in touch with our support",
            sitelink_description2="Available 24/7",
            final_urls=["https://example.com/contact"],
        )

        self.assertEqual(self.mock_asset.sitelink_asset.link_text, "Contact Us")
        self.assertEqual(self.mock_asset.sitelink_asset.description1, "Get in touch with our support")
        self.assertEqual(self.mock_asset.sitelink_asset.description2, "Available 24/7")
        self.mock_asset.final_urls.extend.assert_called_with(["https://example.com/contact"])
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_structured_snippet_asset(self, mock_get_client):
        """Tests creating a STRUCTURED_SNIPPET asset."""
        mock_get_client.return_value = self.mock_client

        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="STRUCTURED_SNIPPET",
            structured_snippet_header="Brands",
            structured_snippet_values=["Google", "DeepMind", "Android"],
        )

        self.assertEqual(self.mock_asset.structured_snippet_asset.header, "Brands")
        self.mock_asset.structured_snippet_asset.values.extend.assert_called_with(["Google", "DeepMind", "Android"])
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_validation_error_missing_fields(self, mock_get_client):
        """Tests that validation correctly errors when required fields are missing."""
        mock_get_client.return_value = self.mock_client

        # Test TEXT missing text_asset_text
        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="TEXT",
        )
        self.assertIn("Error: 'text_asset_text' is required", result)

        # Test SITELINK missing final_urls
        result = await create_asset.create_asset(
            customer_id="1234567890",
            asset_type="SITELINK",
            sitelink_link_text="Link Text",
        )
        self.assertIn("Error: Root-level 'final_urls' is required", result)
