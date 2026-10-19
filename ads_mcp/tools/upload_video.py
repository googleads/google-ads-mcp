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

"""Tool for uploading video assets natively through the Google Ads API."""

import os
from typing import Optional
from ads_mcp.tools.create_asset import assets_mcp
import ads_mcp.utils as utils


@assets_mcp.tool(task=True)
async def upload_video_asset(
    customer_id: str,
    video_title: str,
    video_description: str,
    video_path: str,
    video_privacy: str = "UNLISTED",
    youtube_channel_id: Optional[str] = None,
    validate_only: bool = True,
    checksum: Optional[str] = None,
) -> str:
    """Uploads a video to YouTube natively via the Google Ads API.
    Once a video has been uploaded, it can be used to create a video asset.
    This operation executes via a FastMCP background task to gracefully handle large file uploads.
    Once the upload finishes successfully, using the search tool and querying the `you_tube_video_upload`
    resource matching the returned ID allows you to retrieve the YouTube Video ID and processing status.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `upload_video_asset` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without uploading the video.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `upload_video_asset` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: The ID of the customer (without hyphens).
        video_title: The title you wish your video to have on YouTube.
        video_description: The description text attached to your YouTube video.
        video_path: The absolute path on the local filesystem to the video file to be uploaded.
        video_privacy: The privacy setting of the video on YouTube. Default is UNLISTED. Valid values are: PUBLIC, UNLISTED, PRIVATE. Note: PUBLIC is only allowed for brand channels.
        youtube_channel_id: Optional. The ID of the YouTube channel the video will be uploaded to. If not provided, it will be uploaded to a Google-managed YouTube channel linked to your ads account.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without uploading the video. If False, requires `checksum` from a prior `validate_only=True` call to execute the video upload.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.

    Returns:
        When `validate_only=True`, a JSON proposal containing `change_items` and `checksum`. When `validate_only=False`, a string indicating the successful upload ID, or an error message.
    """

    # 1. Verify existence of the file
    if not os.path.isfile(video_path):
        return f"Error: The video file does not exist at the absolute path: {video_path}"

    ga_client = utils.get_googleads_client()
    youtube_service = ga_client.get_service("YouTubeVideoUploadService")

    # 2. Build the request object
    req = ga_client.get_type("CreateYouTubeVideoUploadRequest")
    req.customer_id = customer_id

    # 3. Build the YouTubeVideoUpload model
    you_tube_video_upload = req.you_tube_video_upload
    you_tube_video_upload.video_title = video_title
    you_tube_video_upload.video_description = video_description

    # Map raw string to privacy enum
    privacy_enum = ga_client.get_type(
        "YouTubeVideoPrivacyEnum"
    ).YouTubeVideoPrivacy
    privacy_upper = video_privacy.upper()
    privacy_level = getattr(privacy_enum, privacy_upper, None)

    if privacy_level is None:
        return f"Error: Invalid 'video_privacy' value '{video_privacy}'. Must be one of: PUBLIC, UNLISTED, PRIVATE."
    you_tube_video_upload.video_privacy = privacy_level

    # Set optional channel id if supplied
    if youtube_channel_id:
        you_tube_video_upload.channel_id = youtube_channel_id

    # 4. Propose & Confirm workflow
    operation_payload = {
        "tool": "upload_video_asset",
        "operation": utils.MutateOperation.CREATE.value,
        "video_title": video_title,
        "video_description": video_description,
        "video_path": video_path,
        "video_privacy": privacy_upper,
        "youtube_channel_id": youtube_channel_id,
    }

    change_items = utils.build_change_items(
        operation=utils.MutateOperation.CREATE.value,
        entity_readable="YouTube Video Upload",
        primary_key_readable=video_title,
        fields={
            "Video Title": video_title,
            "Video Description": video_description,
            "Video Path": video_path,
            "Video Privacy": privacy_upper,
            "YouTube Channel ID": youtube_channel_id,
        },
    )

    def _commit() -> str:
        with open(video_path, "rb") as video_stream:
            response = youtube_service.create_you_tube_video_upload(
                request=req, stream=video_stream
            )

        return f"Successfully uploaded video to Google Ads. ID: {utils.extract_id(response.resource_name)}"

    return utils.propose_and_confirm(
        customer_id=customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=None,
        commit_fn=_commit,
        error_prefix="Failed to upload video",
    )
