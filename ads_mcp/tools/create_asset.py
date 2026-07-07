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

"""Tool for creating Google Ads assets using the AssetService."""

import base64
import os
from typing import List, Dict, Any, Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


def _populate_message(msg, data: Dict[str, Any]) -> None:
    """Recursively populates a proto-plus message from a dictionary."""
    for key, value in data.items():
        if isinstance(value, dict):
            nested_msg = getattr(msg, key)
            _populate_message(nested_msg, value)
        elif isinstance(value, list):
            field_list = getattr(msg, key)
            for item in value:
                if isinstance(item, dict):
                    if hasattr(field_list, "add"):
                        added_element = field_list.add()
                        _populate_message(added_element, item)
                else:
                    field_list.append(item)
        else:
            setattr(msg, key, value)


def _populate_sub_asset(
    asset,
    ga_client,
    type_upper: str,
    final_urls: Optional[List[str]] = None,
    text_asset_text: str = None,
    image_asset_path: str = None,
    image_asset_data: str = None,
    image_asset_mime_type: str = None,
    youtube_video_id: str = None,
    sitelink_link_text: str = None,
    sitelink_description1: str = None,
    sitelink_description2: str = None,
    callout_text: str = None,
    structured_snippet_header: str = None,
    structured_snippet_values: Optional[List[str]] = None,
) -> Optional[str]:
    """Populates specific sub-asset fields based on asset type."""
    if type_upper == "TEXT":
        if not text_asset_text:
            return "Error: 'text_asset_text' is required when 'asset_type' is 'TEXT'."
        asset.text_asset.text = text_asset_text

    elif type_upper == "IMAGE":
        image_bytes = None
        mime_val = None

        mime_enum = ga_client.get_type("MimeTypeEnum").MimeType

        if image_asset_path:
            if not os.path.isfile(image_asset_path):
                return f"Error: Local image file does not exist at path: '{image_asset_path}'."
            try:
                with open(image_asset_path, "rb") as f:
                    image_bytes = f.read()
            except Exception as e:
                return f"Error reading image file from local disk: {e}"

            # Infer MIME type from extension
            ext = os.path.splitext(image_asset_path)[1].lower()
            if ext in [".png"]:
                mime_val = mime_enum.IMAGE_PNG
            elif ext in [".jpg", ".jpeg"]:
                mime_val = mime_enum.IMAGE_JPEG
            elif ext in [".gif"]:
                mime_val = mime_enum.IMAGE_GIF
            else:
                return f"Error: Inferred image extension '{ext}' is unsupported. Must be png, jpg, jpeg, or gif."
        elif image_asset_data:
            if not image_asset_mime_type:
                return "Error: 'image_asset_mime_type' is required when using base64 'image_asset_data'."
            mime_type_upper = image_asset_mime_type.upper()
            if hasattr(mime_enum, mime_type_upper):
                mime_val = getattr(mime_enum, mime_type_upper)
            else:
                return f"Error: Invalid 'image_asset_mime_type' value '{image_asset_mime_type}'."

            try:
                image_bytes = base64.b64decode(image_asset_data)
            except Exception as e:
                return f"Error decoding base64 'image_asset_data': {e}"
        else:
            return "Error: Either 'image_asset_path' or 'image_asset_data' must be provided when 'asset_type' is 'IMAGE'."

        asset.image_asset.data = image_bytes
        asset.image_asset.mime_type = mime_val

    elif type_upper == "YOUTUBE_VIDEO":
        if not youtube_video_id:
            return "Error: 'youtube_video_id' is required when 'asset_type' is 'YOUTUBE_VIDEO'."
        asset.youtube_video_asset.youtube_video_id = youtube_video_id

    elif type_upper == "SITELINK":
        if not sitelink_link_text:
            return "Error: 'sitelink_link_text' is required when 'asset_type' is 'SITELINK'."
        if not final_urls:
            return "Error: Root-level 'final_urls' is required when 'asset_type' is 'SITELINK'."
        asset.sitelink_asset.link_text = sitelink_link_text
        if sitelink_description1:
            asset.sitelink_asset.description1 = sitelink_description1
        if sitelink_description2:
            asset.sitelink_asset.description2 = sitelink_description2

    elif type_upper == "CALLOUT":
        if not callout_text:
            return "Error: 'callout_text' is required when 'asset_type' is 'CALLOUT'."
        asset.callout_asset.callout_text = callout_text

    elif type_upper == "STRUCTURED_SNIPPET":
        if not structured_snippet_header:
            return "Error: 'structured_snippet_header' is required when 'asset_type' is 'STRUCTURED_SNIPPET'."
        if not structured_snippet_values:
            return "Error: 'structured_snippet_values' list is required when 'asset_type' is 'STRUCTURED_SNIPPET'."
        asset.structured_snippet_asset.header = structured_snippet_header
        asset.structured_snippet_asset.values.extend(structured_snippet_values)

    return None


@mcp.tool
async def create_asset(
    customer_id: str,
    asset_type: str,
    name: str = None,
    final_urls: List[str] = None,
    final_mobile_urls: List[str] = None,
    tracking_url_template: str = None,
    final_url_suffix: str = None,
    url_custom_parameters: List[Dict[str, str]] = None,
    # Text Asset
    text_asset_text: str = None,
    # Image Asset
    image_asset_path: str = None,
    image_asset_data: str = None,
    image_asset_mime_type: str = None,
    # YouTube Video Asset
    youtube_video_id: str = None,
    # Sitelink Asset
    sitelink_link_text: str = None,
    sitelink_description1: str = None,
    sitelink_description2: str = None,
    # Callout Asset
    callout_text: str = None,
    # Structured Snippet Asset
    structured_snippet_header: str = None,
    structured_snippet_values: List[str] = None,
    # Fallback/Custom Parameters
    extra_params: Dict[str, Any] = None,
) -> str:
    """Creates a new Google Ads asset under the specified customer account.

    Required & Optional parameters per `asset_type`:
    - **TEXT**: Requires `text_asset_text`.
    - **IMAGE**: Requires either `image_asset_path` (absolute local path) OR `image_asset_data` (base64 encoded string).
      If `image_asset_data` is provided, `image_asset_mime_type` is also required (e.g. 'IMAGE_PNG', 'IMAGE_JPEG', 'IMAGE_GIF').
    - **YOUTUBE_VIDEO**: Requires `youtube_video_id`.
    - **SITELINK**: Requires `sitelink_link_text` and root-level `final_urls`.
      Accepts optional `sitelink_description1` and `sitelink_description2`.
    - **CALLOUT**: Requires `callout_text`.
    - **STRUCTURED_SNIPPET**: Requires `structured_snippet_header` and `structured_snippet_values`.

    Root-level URL and tracking configurations (optional except where noted):
    - `name`: Optional display name for the asset.
    - `final_urls`: Required for SITELINK. A list of URLs.
    - `final_mobile_urls`: List of mobile-specific destination URLs.
    - `tracking_url_template`: Template for constructing a tracking URL.
    - `final_url_suffix`: Suffix appended to the final URL.
    - `url_custom_parameters`: Custom parameters represented as a list of dicts (with 'key' and 'value').

    For any other asset type, configure `extra_params` as a dict representing the sub-asset message fields.

    Args:
        customer_id: Google Ads Customer ID (without hyphens).
        asset_type: Type of the asset (e.g., 'TEXT', 'IMAGE', 'YOUTUBE_VIDEO', 'SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET').
        name: Optional name of the asset.
        final_urls: Optional list of final URLs (required for SITELINK).
        final_mobile_urls: Optional list of final mobile URLs.
        tracking_url_template: Optional tracking URL template.
        final_url_suffix: Optional final URL suffix.
        url_custom_parameters: Optional custom parameters for tracking (list of key-value dicts).
        text_asset_text: Optional text content (required for TEXT type).
        image_asset_path: Optional absolute file path to a local image (supported for IMAGE type).
        image_asset_data: Optional base64 encoded image data (supported for IMAGE type).
        image_asset_mime_type: Optional MIME type (e.g., 'IMAGE_PNG', 'IMAGE_JPEG', 'IMAGE_GIF'; required if image_asset_data is used).
        youtube_video_id: Optional YouTube 11-character video ID (required for YOUTUBE_VIDEO type).
        sitelink_link_text: Optional link text (required for SITELINK type).
        sitelink_description1: Optional sitelink line 1 description.
        sitelink_description2: Optional sitelink line 2 description.
        callout_text: Optional callout text (required for CALLOUT type).
        structured_snippet_header: Optional structured snippet header category (required for STRUCTURED_SNIPPET type).
        structured_snippet_values: Optional structured snippet list of values (required for STRUCTURED_SNIPPET type).
        extra_params: Optional dict representing nested parameters for less common asset types.

    Returns:
        A string indicating successful asset creation and its ID, or an error message.
    """
    ga_client = utils.get_googleads_client()
    asset_service = ga_client.get_service("AssetService")

    # Build Asset operation
    asset_op = ga_client.get_type("AssetOperation")
    asset = asset_op.create

    # 1. Root-level settings
    if name:
        asset.name = name
    if final_urls:
        asset.final_urls.extend(final_urls)
    if final_mobile_urls:
        asset.final_mobile_urls.extend(final_mobile_urls)
    if tracking_url_template:
        asset.tracking_url_template = tracking_url_template
    if final_url_suffix:
        asset.final_url_suffix = final_url_suffix

    if url_custom_parameters:
        for param_dict in url_custom_parameters:
            key = param_dict.get("key")
            value = param_dict.get("value")
            if not key or not value:
                return "Error: Each item in 'url_custom_parameters' must contain both 'key' and 'value'."
            param = ga_client.get_type("CustomParameter")
            param.key = key
            param.value = value
            asset.url_custom_parameters.append(param)

    # Parse and validate AssetType
    asset_type_enum = ga_client.get_type("AssetTypeEnum").AssetType
    type_upper = asset_type.upper()
    if hasattr(asset_type_enum, type_upper):
        asset.type_ = getattr(asset_type_enum, type_upper)
    else:
        valid_types = [t.name for t in asset_type_enum if t.name not in ["UNSPECIFIED", "UNKNOWN"]]
        return f"Error: Invalid 'asset_type' value '{asset_type}'. Must be one of: {', '.join(valid_types)}."

    # 2. Populate Sub-Asset details
    err = _populate_sub_asset(
        asset,
        ga_client,
        type_upper,
        final_urls=final_urls,
        text_asset_text=text_asset_text,
        image_asset_path=image_asset_path,
        image_asset_data=image_asset_data,
        image_asset_mime_type=image_asset_mime_type,
        youtube_video_id=youtube_video_id,
        sitelink_link_text=sitelink_link_text,
        sitelink_description1=sitelink_description1,
        sitelink_description2=sitelink_description2,
        callout_text=callout_text,
        structured_snippet_header=structured_snippet_header,
        structured_snippet_values=structured_snippet_values,
    )
    if err:
        return err

    # 3. Fallback/Custom parameters populator
    if extra_params:
        field_name = f"{type_upper.lower()}_asset"
        if hasattr(asset, field_name):
            sub_msg = getattr(asset, field_name)
            try:
                _populate_message(sub_msg, extra_params)
            except Exception as e:
                return f"Error populating dynamic 'extra_params' for '{field_name}': {e}"
        else:
            return f"Error: Asset type field '{field_name}' does not exist on the Asset resource."

    # 4. Mutate
    try:
        response = asset_service.mutate_assets(
            customer_id=customer_id, operations=[asset_op]
        )
        created_rn = response.results[0].resource_name
        created_id = utils.extract_id(created_rn)
        return f"Successfully created asset. ID: {created_id}"
    except Exception as e:
        utils.logger.error(f"Failed to create asset: {e}")
        return f"Failed to create asset: {e}"
