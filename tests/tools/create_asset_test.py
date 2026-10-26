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
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, create_autospec, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v25.services.services.asset_service import (
    AssetServiceClient,
)
from google.auth.credentials import AnonymousCredentials
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
from ads_mcp.tools import create_asset


class TestCreateAsset(unittest.TestCase):
    """Test cases for the create asset tool."""

    @classmethod
    def setUpClass(cls):
        cls.real_ga_client = GoogleAdsClient(
            credentials=AnonymousCredentials(),
            developer_token="fake-token",
            use_proto_plus=True,
        )

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_asset_service = create_autospec(
            AssetServiceClient, instance=True
        )
        self.mock_client.get_service.return_value = self.mock_asset_service
        self.mock_client.get_type.side_effect = self.real_ga_client.get_type

        # Setup default successful response
        self.mock_response = MagicMock()
        mock_result = MagicMock()
        mock_result.resource_name = "customers/1234567890/assets/456"
        self.mock_response.results = [mock_result]
        self.mock_asset_service.mutate_assets.return_value = self.mock_response

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_text_asset_and_customer_sanitization(self, mock_get_client):
        """Tests TEXT asset propose/confirm, hyphenated customer_id, login_customer_id, and interceptor."""
        mock_get_client.return_value = self.mock_client

        # 1. Propose (validate_only=True by default)
        propose_result = create_asset.create_asset(
            customer_id="123-456-7890",
            asset_type="TEXT",
            name="My Text Asset",
            text_asset_text="Sign up today!",
            login_customer_id="999-888-7777",
        )
        mock_get_client.assert_called_with(login_customer_id="999-888-7777")
        _, svc_kwargs = self.mock_client.get_service.call_args
        self.assertEqual(len(svc_kwargs["interceptors"]), 1)
        self.assertIsInstance(
            svc_kwargs["interceptors"][0], MCPHeaderInterceptor
        )

        proposal = json.loads(propose_result)
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertTrue(proposal["validate_only"])
        self.assertEqual(proposal["customer_id"], "1234567890")
        checksum = proposal["checksum"]
        self.assertTrue(checksum)

        propose_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        self.assertEqual(propose_req.customer_id, "1234567890")
        self.assertTrue(propose_req.validate_only)
        self.assertEqual(propose_req.operations[0].create.name, "My Text Asset")
        self.assertEqual(
            propose_req.operations[0].create.text_asset.text, "Sign up today!"
        )

        # 2. Confirm (validate_only=False with checksum)
        result = create_asset.create_asset(
            customer_id="123-456-7890",
            asset_type="TEXT",
            name="My Text Asset",
            text_asset_text="Sign up today!",
            login_customer_id="999-888-7777",
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        self.assertFalse(commit_req.validate_only)
        self.assertIn("Successfully created asset", result)
        self.assertIn("ID: 456", result)

    @patch.dict(os.environ, {}, clear=True)
    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_image_asset_local(self, mock_get_client):
        """Tests creating an IMAGE asset from a real temporary local file."""
        mock_get_client.return_value = self.mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "logo.png")
            with open(img_path, "wb") as f:
                f.write(b"fakeimagebytes")

            propose_res = create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                name="My Local Image",
                image_asset_path=img_path,
            )
            proposal = json.loads(propose_res)
            checksum = proposal["checksum"]

            result = create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                name="My Local Image",
                image_asset_path=img_path,
                validate_only=False,
                checksum=checksum,
            )

            commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
                "request"
            ]
            created = commit_req.operations[0].create
            self.assertEqual(created.image_asset.data, b"fakeimagebytes")
            self.assertEqual(created.image_asset.mime_type.name, "IMAGE_PNG")
            self.assertIn("Successfully created asset", result)

            # Modifying the image bytes on disk invalidates the checksum
            with open(img_path, "wb") as f:
                f.write(b"tampered_image_bytes")
            with self.assertRaisesRegex(
                ToolError, "Invalid or mismatched checksum"
            ):
                create_asset.create_asset(
                    customer_id="1234567890",
                    asset_type="IMAGE",
                    name="My Local Image",
                    image_asset_path=img_path,
                    validate_only=False,
                    checksum=checksum,
                )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_image_asset_base64(self, mock_get_client):
        """Tests creating an IMAGE asset using base64 encoded data."""
        mock_get_client.return_value = self.mock_client
        b64_data = base64.b64encode(b"fakeb64bytes").decode("utf-8")

        propose_res = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="IMAGE",
            name="My Base64 Image",
            image_asset_data=b64_data,
            image_asset_mime_type="IMAGE_JPEG",
        )
        checksum = json.loads(propose_res)["checksum"]

        result = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="IMAGE",
            name="My Base64 Image",
            image_asset_data=b64_data,
            image_asset_mime_type="IMAGE_JPEG",
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        created = commit_req.operations[0].create
        self.assertEqual(created.image_asset.data, b"fakeb64bytes")
        self.assertEqual(created.image_asset.mime_type.name, "IMAGE_JPEG")
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_sitelink_and_url_custom_params(self, mock_get_client):
        """Tests creating a SITELINK asset with descriptions, URLs, and custom tracking params."""
        mock_get_client.return_value = self.mock_client

        kwargs = {
            "customer_id": "1234567890",
            "asset_type": "SITELINK",
            "name": "Contact Us Sitelink",
            "sitelink_link_text": "Contact Us",
            "sitelink_description1": "Get in touch with our support",
            "sitelink_description2": "Available 24/7",
            "final_urls": ["https://example.com/contact"],
            "url_custom_parameters": [{"key": "src", "value": "mcp"}],
        }
        propose_res = create_asset.create_asset(**kwargs)
        checksum = json.loads(propose_res)["checksum"]

        result = create_asset.create_asset(
            **kwargs,
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        created = commit_req.operations[0].create
        self.assertEqual(created.sitelink_asset.link_text, "Contact Us")
        self.assertEqual(
            created.sitelink_asset.description1,
            "Get in touch with our support",
        )
        self.assertEqual(created.sitelink_asset.description2, "Available 24/7")
        self.assertEqual(
            list(created.final_urls), ["https://example.com/contact"]
        )
        self.assertEqual(created.url_custom_parameters[0].key, "src")
        self.assertEqual(created.url_custom_parameters[0].value, "mcp")
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_structured_snippet_asset(self, mock_get_client):
        """Tests creating a STRUCTURED_SNIPPET asset."""
        mock_get_client.return_value = self.mock_client

        propose_res = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="STRUCTURED_SNIPPET",
            structured_snippet_header="Brands",
            structured_snippet_values=["Google", "DeepMind", "Android"],
        )
        checksum = json.loads(propose_res)["checksum"]

        result = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="STRUCTURED_SNIPPET",
            structured_snippet_header="Brands",
            structured_snippet_values=["Google", "DeepMind", "Android"],
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        created = commit_req.operations[0].create
        self.assertEqual(created.structured_snippet_asset.header, "Brands")
        self.assertEqual(
            list(created.structured_snippet_asset.values),
            ["Google", "DeepMind", "Android"],
        )
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_price_asset_via_extra_params(self, mock_get_client):
        """Tests creating a complex sub-asset (PRICE) with repeated messages and enums via extra_params."""
        mock_get_client.return_value = self.mock_client

        extra_params = {
            "type": "BRANDS",
            "price_qualifier": "FROM",
            "language_code": "en",
            "price_offerings": [
                {
                    "header": "Starter Plan",
                    "description": "Great for small teams",
                    "price": {
                        "amount_micros": 9990000,
                        "currency_code": "USD",
                    },
                    "unit": "PER_MONTH",
                    "final_url": "https://example.com/starter",
                }
            ],
        }
        propose_res = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="PRICE",
            name="Pricing Table",
            extra_params=extra_params,
        )
        checksum = json.loads(propose_res)["checksum"]

        result = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="PRICE",
            name="Pricing Table",
            extra_params=extra_params,
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_asset_service.mutate_assets.call_args.kwargs[
            "request"
        ]
        price_asset = commit_req.operations[0].create.price_asset
        self.assertEqual(price_asset.type_.name, "BRANDS")
        self.assertEqual(price_asset.price_qualifier.name, "FROM")
        self.assertEqual(len(price_asset.price_offerings), 1)
        self.assertEqual(price_asset.price_offerings[0].header, "Starter Plan")
        self.assertEqual(
            price_asset.price_offerings[0].price.amount_micros, 9990000
        )
        self.assertIn("Successfully created asset", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_validation_and_security_errors(self, mock_get_client):
        """Tests validation and security guardrails raise ToolError."""
        mock_get_client.return_value = self.mock_client

        # Missing text_asset_text
        with self.assertRaisesRegex(ToolError, "'text_asset_text' is required"):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="TEXT",
            )

        # Missing final_urls on SITELINK
        with self.assertRaisesRegex(
            ToolError, "Root-level 'final_urls' is required"
        ):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="SITELINK",
                sitelink_link_text="Link Text",
            )

        # UNSPECIFIED asset_type rejected
        with self.assertRaisesRegex(ToolError, "Invalid 'asset_type'"):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="UNSPECIFIED",
            )

        # Non-dedicated asset_type missing extra_params rejected
        with self.assertRaisesRegex(ToolError, "'extra_params' is required"):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="PRICE",
            )

        # Both image_asset_path and image_asset_data rejected
        with self.assertRaisesRegex(ToolError, "not both"):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                image_asset_path="/tmp/a.png",
                image_asset_data=base64.b64encode(b"x").decode("utf-8"),
                image_asset_mime_type="IMAGE_PNG",
            )

        # Non-image MIME type rejected
        with self.assertRaisesRegex(
            ToolError, "Invalid 'image_asset_mime_type'"
        ):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                image_asset_data=base64.b64encode(b"x").decode("utf-8"),
                image_asset_mime_type="AUDIO_MP3",
            )

        # Invalid base64 rejected
        with self.assertRaisesRegex(
            ToolError, "Error decoding base64 'image_asset_data'"
        ):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="IMAGE",
                image_asset_data="!!!not-base64!!!",
                image_asset_mime_type="IMAGE_PNG",
            )

        # Remote OAuth mode blocks local image_asset_path
        with patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET": "csecret",
            },
        ):
            with self.assertRaisesRegex(
                ToolError, "only supported in local stdio mode"
            ):
                create_asset.create_asset(
                    customer_id="1234567890",
                    asset_type="IMAGE",
                    image_asset_path="/tmp/logo.png",
                )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_confirm_missing_or_mismatched_checksum_rejected(
        self, mock_get_client
    ):
        """Tests that validate_only=False raises ToolError on missing or mismatched checksums."""
        mock_get_client.return_value = self.mock_client

        # Missing checksum
        with self.assertRaisesRegex(
            ToolError,
            "checksum from a previous validate_only=True call is required",
        ):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="TEXT",
                name="My Text Asset",
                text_asset_text="Sign up today!",
                validate_only=False,
            )
        self.mock_asset_service.mutate_assets.assert_not_called()

        # Obtain valid checksum, then modify text_asset_text on confirm
        propose_res = create_asset.create_asset(
            customer_id="1234567890",
            asset_type="TEXT",
            name="My Text Asset",
            text_asset_text="Sign up today!",
            validate_only=True,
        )
        checksum = json.loads(propose_res)["checksum"]
        self.assertEqual(self.mock_asset_service.mutate_assets.call_count, 1)

        with self.assertRaisesRegex(
            ToolError, "Invalid or mismatched checksum"
        ):
            create_asset.create_asset(
                customer_id="1234567890",
                asset_type="TEXT",
                name="My Text Asset",
                text_asset_text="Modified unapproved text!",
                validate_only=False,
                checksum=checksum,
            )
        self.assertEqual(self.mock_asset_service.mutate_assets.call_count, 1)


if __name__ == "__main__":
    unittest.main()
