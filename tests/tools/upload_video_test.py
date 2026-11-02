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

"""Test cases for the upload_video tool."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.auth.credentials import AnonymousCredentials
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
from ads_mcp.tools import upload_video


class TestUploadVideo(unittest.IsolatedAsyncioTestCase):
    """Test cases for the upload video tool."""

    @classmethod
    def setUpClass(cls):
        cls.real_ga_client = GoogleAdsClient(
            credentials=AnonymousCredentials(),
            developer_token="fake-token",
            use_proto_plus=True,
        )

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_youtube_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_youtube_service
        self.mock_client.get_type.side_effect = self.real_ga_client.get_type

        mock_response = MagicMock()
        mock_response.resource_name = (
            "customers/1234567890/youTubeVideoUploads/456"
        )
        self.mock_youtube_service.create_you_tube_video_upload.return_value = (
            mock_response
        )

    @patch.dict(os.environ, {}, clear=True)
    @patch("ads_mcp.utils.get_googleads_client")
    async def test_upload_video_asset(self, mock_get_client):
        """Tests that upload_video_asset proposes (validate_only=True) and uploads (validate_only=False)."""
        mock_get_client.return_value = self.mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fakevideodata")

            # 1. Propose phase (validate_only=True by default) does not stream video yet
            propose_res = await upload_video.upload_video_asset(
                customer_id="123-456-7890",
                video_title="My Test Video",
                video_description="This is a test video description.",
                video_path=video_path,
                video_privacy="PUBLIC",
                youtube_channel_id="UC123456",
                login_customer_id="999-888-7777",
            )
            mock_get_client.assert_called_with(login_customer_id="999-888-7777")
            _, svc_kwargs = self.mock_client.get_service.call_args
            self.assertIsInstance(
                svc_kwargs["interceptors"][0], MCPHeaderInterceptor
            )

            proposal = json.loads(propose_res)
            self.assertEqual(proposal["status"], "PROPOSED")
            self.assertTrue(proposal["validate_only"])
            self.assertEqual(proposal["customer_id"], "1234567890")
            checksum = proposal["checksum"]
            self.assertTrue(checksum)
            self.mock_youtube_service.create_you_tube_video_upload.assert_not_called()

            # 2. Confirm phase (validate_only=False with valid checksum) streams video
            result = await upload_video.upload_video_asset(
                customer_id="123-456-7890",
                video_title="My Test Video",
                video_description="This is a test video description.",
                video_path=video_path,
                video_privacy="PUBLIC",
                youtube_channel_id="UC123456",
                login_customer_id="999-888-7777",
                validate_only=False,
                checksum=checksum,
            )

            call_kwargs = (
                self.mock_youtube_service.create_you_tube_video_upload.call_args.kwargs
            )
            req = call_kwargs["request"]
            self.assertEqual(req.customer_id, "1234567890")
            upload_metadata = req.you_tube_video_upload
            self.assertEqual(upload_metadata.video_title, "My Test Video")
            self.assertEqual(
                upload_metadata.video_description,
                "This is a test video description.",
            )
            self.assertEqual(upload_metadata.video_privacy.name, "PUBLIC")
            self.assertEqual(upload_metadata.channel_id, "UC123456")

            self.mock_youtube_service.create_you_tube_video_upload.assert_called_once()
            self.assertIn("Successfully uploaded video", result)
            self.assertIn("ID: 456", result)

    @patch.dict(os.environ, {}, clear=True)
    @patch("ads_mcp.utils.get_googleads_client")
    async def test_upload_video_asset_checksum_and_toctou_enforcement(
        self, mock_get_client
    ):
        """Tests missing/mismatched checksums and TOCTOU file modification rejection."""
        mock_get_client.return_value = self.mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"initial_video_bytes")

            # Missing checksum
            with self.assertRaisesRegex(
                ToolError,
                "checksum from a previous validate_only=True call is required",
            ):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="My Test Video",
                    video_description="Description",
                    video_path=video_path,
                    validate_only=False,
                )
            self.mock_youtube_service.create_you_tube_video_upload.assert_not_called()

            # Valid proposal
            propose_res = await upload_video.upload_video_asset(
                customer_id="1234567890",
                video_title="My Test Video",
                video_description="Description",
                video_path=video_path,
                validate_only=True,
            )
            checksum = json.loads(propose_res)["checksum"]

            # Mismatched title
            with self.assertRaisesRegex(
                ToolError, "Invalid or mismatched checksum"
            ):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="Modified Video Title",
                    video_description="Description",
                    video_path=video_path,
                    validate_only=False,
                    checksum=checksum,
                )

            # TOCTOU: swapping file contents on disk invalidates checksum via st_size/st_mtime_ns
            with open(video_path, "wb") as f:
                f.write(b"swapped_larger_video_bytes_payload")
            with self.assertRaisesRegex(
                ToolError, "Invalid or mismatched checksum"
            ):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="My Test Video",
                    video_description="Description",
                    video_path=video_path,
                    validate_only=False,
                    checksum=checksum,
                )
            self.mock_youtube_service.create_you_tube_video_upload.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("ads_mcp.utils.get_googleads_client")
    async def test_upload_video_validation_and_security_errors(
        self, mock_get_client
    ):
        """Tests missing files, disallowed extensions, UNSPECIFIED privacy, and remote OAuth mode."""
        mock_get_client.return_value = self.mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_mp4 = os.path.join(tmpdir, "missing_video.mp4")
            with self.assertRaisesRegex(
                ToolError, "The video file does not exist"
            ):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="My Test Video",
                    video_description="Description",
                    video_path=missing_mp4,
                )

            bad_ext = os.path.join(tmpdir, "notes.txt")
            with open(bad_ext, "wb") as f:
                f.write(b"text")
            with self.assertRaisesRegex(
                ToolError, "Unsupported video file extension"
            ):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="My Test Video",
                    video_description="Description",
                    video_path=bad_ext,
                )

            valid_mp4 = os.path.join(tmpdir, "valid.mp4")
            with open(valid_mp4, "wb") as f:
                f.write(b"bytes")
            with self.assertRaisesRegex(ToolError, "Invalid 'video_privacy'"):
                await upload_video.upload_video_asset(
                    customer_id="1234567890",
                    video_title="My Test Video",
                    video_description="Description",
                    video_path=valid_mp4,
                    video_privacy="UNSPECIFIED",  # type: ignore[arg-type]
                )

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
                    await upload_video.upload_video_asset(
                        customer_id="1234567890",
                        video_title="My Test Video",
                        video_description="Description",
                        video_path=valid_mp4,
                    )


if __name__ == "__main__":
    unittest.main()
