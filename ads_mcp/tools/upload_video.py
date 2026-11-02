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

import asyncio
from enum import Enum
import os

from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp import propose_and_confirm as pac
from ads_mcp.tools import assets_mcp
import ads_mcp.utils as utils

_ALLOWED_VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".avi",
        ".flv",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ogg",
        ".webm",
        ".wmv",
    }
)


class VideoPrivacy(str, Enum):
    """Supported YouTube video privacy settings."""

    PUBLIC = "PUBLIC"
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"


@assets_mcp.tool(
    task=True,
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def upload_video_asset(
    customer_id: str | int,
    video_title: str,
    video_description: str,
    video_path: str,
    video_privacy: VideoPrivacy = VideoPrivacy.UNLISTED,
    youtube_channel_id: str | None = None,
    login_customer_id: str | int | None = None,
    validate_only: bool = True,
    checksum: str | None = None,
) -> str:
    """Uploads a video to YouTube natively via the Google Ads API.

    Once a video has been uploaded, it can be used to create a video asset.
    This operation executes via a FastMCP background task to gracefully handle large file uploads
    (supported in local stdio mode only).
    Once the upload finishes successfully, using the search tool and querying the `you_tube_video_upload`
    resource matching the returned ID allows you to retrieve the YouTube Video ID and processing status.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `upload_video_asset` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without uploading the video.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `upload_video_asset` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (digits or hyphenated, e.g. '1234567890').
        video_title: The title you wish your video to have on YouTube.
        video_description: The description text attached to your YouTube video.
        video_path: The absolute path on the local filesystem to the video file to be uploaded (local stdio mode only).
        video_privacy: The privacy setting of the video on YouTube. Default is UNLISTED. Valid values are: PUBLIC, UNLISTED, PRIVATE. Note: PUBLIC is only allowed for brand channels.
        youtube_channel_id: Optional. The ID of the YouTube channel the video will be uploaded to. If not provided, it will be uploaded to a Google-managed YouTube channel linked to your ads account.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without uploading the video. If False, requires `checksum` from a prior `validate_only=True` call to execute the video upload.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.
    """
    cleaned_customer_id = utils.clean_customer_id(customer_id)
    if not cleaned_customer_id:
        raise ToolError("Error: 'customer_id' must contain digits.")

    if utils.is_remote_oauth_mode():
        raise ToolError(
            "Error: 'video_path' is only supported in local stdio mode."
        )

    resolved_path = os.path.realpath(video_path)
    ext = os.path.splitext(resolved_path)[1].lower()
    if ext not in _ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(_ALLOWED_VIDEO_EXTENSIONS))
        raise ToolError(
            f"Error: Unsupported video file extension '{ext}'. Must be one of: {allowed}."
        )

    if not os.path.isfile(resolved_path):
        raise ToolError(
            f"Error: The video file does not exist at the path: {video_path}"
        )

    try:
        file_stat = os.stat(resolved_path)
    except OSError as exc:
        raise ToolError(
            f"Error inspecting video file at '{video_path}': {exc}"
        ) from exc

    privacy_upper = (
        video_privacy.value
        if isinstance(video_privacy, VideoPrivacy)
        else str(video_privacy).upper()
    )
    if privacy_upper not in VideoPrivacy.__members__:
        raise ToolError(
            f"Error: Invalid 'video_privacy' value '{video_privacy}'. "
            "Must be one of: PUBLIC, UNLISTED, PRIVATE."
        )

    ga_client = utils.get_googleads_client(login_customer_id=login_customer_id)
    youtube_service = utils.get_googleads_service_from_client(
        ga_client, "YouTubeVideoUploadService"
    )

    req = ga_client.get_type("CreateYouTubeVideoUploadRequest")
    req.customer_id = cleaned_customer_id

    you_tube_video_upload = req.you_tube_video_upload
    you_tube_video_upload.video_title = video_title
    you_tube_video_upload.video_description = video_description

    privacy_enum = ga_client.get_type(
        "YouTubeVideoPrivacyEnum"
    ).YouTubeVideoPrivacy
    you_tube_video_upload.video_privacy = getattr(privacy_enum, privacy_upper)

    if youtube_channel_id:
        you_tube_video_upload.channel_id = youtube_channel_id

    # Bind file size and mtime into operation_payload to prevent TOCTOU file swaps
    # between validate_only=True and validate_only=False without reading GBs into memory.
    operation_payload = {
        "tool": "upload_video_asset",
        "operation": utils.MutateOperation.CREATE.value,
        "video_title": video_title,
        "video_description": video_description,
        "video_path": resolved_path,
        "video_size_bytes": file_stat.st_size,
        "video_mtime_ns": file_stat.st_mtime_ns,
        "video_privacy": privacy_upper,
        "youtube_channel_id": youtube_channel_id,
    }

    change_items = pac.build_change_items(
        operation=utils.MutateOperation.CREATE.value,
        entity_readable="YouTube Video Upload",
        primary_key_readable=video_title,
        fields={
            "Video Title": video_title,
            "Video Description": video_description,
            "Video Path": resolved_path,
            "Video Size (bytes)": file_stat.st_size,
            "Video Privacy": privacy_upper,
            "YouTube Channel ID": youtube_channel_id,
        },
    )

    def _commit() -> str:
        with open(resolved_path, "rb") as video_stream:
            response = youtube_service.create_you_tube_video_upload(
                request=req, stream=video_stream
            )
        return (
            "Successfully uploaded video to Google Ads. "
            f"ID: {utils.extract_id(response.resource_name)}"
        )

    return await asyncio.to_thread(
        pac.propose_and_confirm,
        customer_id=cleaned_customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=None,
        commit_fn=_commit,
        error_prefix="Failed to upload video",
    )
