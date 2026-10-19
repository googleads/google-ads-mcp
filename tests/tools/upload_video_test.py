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
import unittest
from unittest.mock import MagicMock, patch, mock_open

from ads_mcp.tools import upload_video


class TestUploadVideo(unittest.IsolatedAsyncioTestCase):
    """Test cases for the upload video tool."""

    @patch("ads_mcp.utils.get_googleads_client")
    @patch("os.path.isfile")
    async def test_upload_video_asset(self, mock_isfile, mock_get_client):
        """Tests that the upload video function proposes (validate_only=True) and uploads (validate_only=False)."""
        # Setup mocks
        mock_isfile.return_value = True
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_youtube_service = MagicMock()
        mock_client.get_service.return_value = mock_youtube_service

        mock_request = MagicMock()
        mock_privacy_enum = MagicMock()
        mock_privacy_enum.YouTubeVideoPrivacy.UNLISTED = "UNLISTED"
        mock_privacy_enum.YouTubeVideoPrivacy.PUBLIC = "PUBLIC"

        def get_type_mock(type_name):
            if type_name == "CreateYouTubeVideoUploadRequest":
                return mock_request
            elif type_name == "YouTubeVideoPrivacyEnum":
                return mock_privacy_enum
            return MagicMock()

        mock_client.get_type.side_effect = get_type_mock

        mock_response = MagicMock()
        mock_response.resource_name = "customers/123/youtubeVideoAssets/456"
        mock_youtube_service.create_you_tube_video_upload.return_value = (
            mock_response
        )

        # 1. Propose phase (validate_only=True by default) does not stream video yet
        propose_res = await upload_video.upload_video_asset(
            customer_id="1234567890",
            video_title="My Test Video",
            video_description="This is a test video description.",
            video_path="/fake/path/video.mp4",
            video_privacy="PUBLIC",
            youtube_channel_id="UC123456",
        )
        proposal = json.loads(propose_res)
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertTrue(proposal["validate_only"])
        checksum = proposal["checksum"]
        self.assertTrue(checksum)
        mock_youtube_service.create_you_tube_video_upload.assert_not_called()

        # 2. Confirm phase (validate_only=False with valid checksum) streams video
        m = mock_open(read_data=b"fakevideodata")
        with patch("builtins.open", m):
            result = await upload_video.upload_video_asset(
                customer_id="1234567890",
                video_title="My Test Video",
                video_description="This is a test video description.",
                video_path="/fake/path/video.mp4",
                video_privacy="PUBLIC",
                youtube_channel_id="UC123456",
                validate_only=False,
                checksum=checksum,
            )

            # Assertions
            self.assertEqual(mock_request.customer_id, "1234567890")
            upload_metadata = mock_request.you_tube_video_upload
            self.assertEqual(upload_metadata.video_title, "My Test Video")
            self.assertEqual(
                upload_metadata.video_description,
                "This is a test video description.",
            )
            self.assertEqual(upload_metadata.video_privacy, "PUBLIC")
            self.assertEqual(upload_metadata.channel_id, "UC123456")

            mock_youtube_service.create_you_tube_video_upload.assert_called_once()

            self.assertIn("Successfully uploaded video", result)
            self.assertIn("ID: 456", result)

    @patch("ads_mcp.utils.get_googleads_client")
    @patch("os.path.isfile")
    async def test_upload_video_asset_checksum_enforcement(
        self, mock_isfile, mock_get_client
    ):
        """Tests that missing or mismatched checksums are rejected without uploading."""
        mock_isfile.return_value = True
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_youtube_service = MagicMock()
        mock_client.get_service.return_value = mock_youtube_service

        mock_privacy_enum = MagicMock()
        mock_privacy_enum.YouTubeVideoPrivacy.UNLISTED = "UNLISTED"
        mock_client.get_type.side_effect = lambda name: (
            mock_privacy_enum
            if name == "YouTubeVideoPrivacyEnum"
            else MagicMock()
        )

        # Missing checksum
        res_missing = await upload_video.upload_video_asset(
            customer_id="1234567890",
            video_title="My Test Video",
            video_description="Description",
            video_path="/fake/path/video.mp4",
            validate_only=False,
        )
        self.assertIn(
            "checksum from a previous validate_only=True call is required",
            res_missing,
        )
        mock_youtube_service.create_you_tube_video_upload.assert_not_called()

        # Mismatched checksum
        propose_res = await upload_video.upload_video_asset(
            customer_id="1234567890",
            video_title="My Test Video",
            video_description="Description",
            video_path="/fake/path/video.mp4",
            validate_only=True,
        )
        checksum = json.loads(propose_res)["checksum"]

        res_mismatch = await upload_video.upload_video_asset(
            customer_id="1234567890",
            video_title="Modified Video Title",
            video_description="Description",
            video_path="/fake/path/video.mp4",
            validate_only=False,
            checksum=checksum,
        )
        self.assertIn("Invalid or mismatched checksum", res_mismatch)
        mock_youtube_service.create_you_tube_video_upload.assert_not_called()

    @patch("os.path.isfile")
    async def test_upload_video_asset_file_not_found(self, mock_isfile):
        """Tests that the function returns an error when the video file is not found."""
        mock_isfile.return_value = False

        result = await upload_video.upload_video_asset(
            customer_id="1234567890",
            video_title="My Test Video",
            video_description="This is a test video description.",
            video_path="/fake/path/missing_video.mp4",
        )

        self.assertIn("Error: The video file does not exist", result)
