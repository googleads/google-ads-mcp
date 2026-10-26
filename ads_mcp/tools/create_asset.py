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
from typing import Any

from fastmcp.exceptions import ToolError
from google.protobuf.json_format import ParseDict
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict

from ads_mcp import propose_and_confirm as pac
from ads_mcp.tools import assets_mcp
import ads_mcp.utils as utils

# Safety ceiling before reading local or base64 image data into memory (20 MB).
_MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024

_DEDICATED_ASSET_TYPES = frozenset(
    {
        "TEXT",
        "IMAGE",
        "YOUTUBE_VIDEO",
        "SITELINK",
        "CALLOUT",
        "STRUCTURED_SNIPPET",
    }
)

_EXTENSION_TO_MIME_NAME = {
    ".png": "IMAGE_PNG",
    ".jpg": "IMAGE_JPEG",
    ".jpeg": "IMAGE_JPEG",
    ".gif": "IMAGE_GIF",
}


class UrlCustomParameter(TypedDict):
    """Key-value pair for custom tracking URL parameters."""

    key: str
    value: str


def _populate_sub_asset(
    asset: Any,
    ga_client: Any,
    type_upper: str,
    final_urls: list[str] | None = None,
    text_asset_text: str | None = None,
    image_asset_path: str | None = None,
    image_asset_data: str | None = None,
    image_asset_mime_type: str | None = None,
    youtube_video_id: str | None = None,
    sitelink_link_text: str | None = None,
    sitelink_description1: str | None = None,
    sitelink_description2: str | None = None,
    callout_text: str | None = None,
    structured_snippet_header: str | None = None,
    structured_snippet_values: list[str] | None = None,
) -> str | None:
    """Populates specific sub-asset fields based on asset type.

    Returns:
        The resolved image MIME type name when ``type_upper == 'IMAGE'``,
        otherwise ``None``.
    """
    if type_upper == "TEXT":
        if not text_asset_text:
            raise ToolError(
                "Error: 'text_asset_text' is required when 'asset_type' is 'TEXT'."
            )
        asset.text_asset.text = text_asset_text
        return None

    if type_upper == "IMAGE":
        if image_asset_path and image_asset_data:
            raise ToolError(
                "Error: Provide either 'image_asset_path' or 'image_asset_data', not both."
            )

        mime_enum = ga_client.get_type("MimeTypeEnum").MimeType
        valid_image_mimes = {
            m.name: m for m in mime_enum if m.name.startswith("IMAGE_")
        }

        if image_asset_path:
            if utils.is_remote_oauth_mode():
                raise ToolError(
                    "Error: 'image_asset_path' is only supported in local stdio mode; "
                    "pass base64-encoded 'image_asset_data' instead."
                )

            resolved_path = os.path.realpath(image_asset_path)
            ext = os.path.splitext(resolved_path)[1].lower()
            mime_name = _EXTENSION_TO_MIME_NAME.get(ext)
            if mime_name is None:
                raise ToolError(
                    f"Error: Inferred image extension '{ext}' is unsupported. "
                    "Must be png, jpg, jpeg, or gif."
                )

            if not os.path.isfile(resolved_path):
                raise ToolError(
                    f"Error: Local image file does not exist at path: '{image_asset_path}'."
                )

            try:
                with open(resolved_path, "rb") as f:
                    image_bytes = f.read(_MAX_IMAGE_SIZE_BYTES + 1)
            except OSError as exc:
                raise ToolError(
                    f"Error reading image file from local disk: {exc}"
                ) from exc

            if len(image_bytes) > _MAX_IMAGE_SIZE_BYTES:
                raise ToolError(
                    f"Error: Image file exceeds maximum allowed size of {_MAX_IMAGE_SIZE_BYTES} bytes."
                )
            mime_val = valid_image_mimes[mime_name]

        elif image_asset_data:
            if not image_asset_mime_type:
                raise ToolError(
                    "Error: 'image_asset_mime_type' is required when using base64 'image_asset_data'."
                )
            mime_name = image_asset_mime_type.upper()
            mime_val = valid_image_mimes.get(mime_name)
            if mime_val is None:
                allowed = ", ".join(sorted(valid_image_mimes))
                raise ToolError(
                    f"Error: Invalid 'image_asset_mime_type' value '{image_asset_mime_type}'. "
                    f"Must be one of: {allowed}."
                )

            try:
                image_bytes = base64.b64decode(image_asset_data, validate=True)
            except Exception as exc:
                raise ToolError(
                    f"Error decoding base64 'image_asset_data': {exc}"
                ) from exc

            if len(image_bytes) > _MAX_IMAGE_SIZE_BYTES:
                raise ToolError(
                    f"Error: Decoded image data exceeds maximum allowed size of {_MAX_IMAGE_SIZE_BYTES} bytes."
                )
        else:
            raise ToolError(
                "Error: Either 'image_asset_path' or 'image_asset_data' must be provided "
                "when 'asset_type' is 'IMAGE'."
            )

        asset.image_asset.data = image_bytes
        asset.image_asset.mime_type = mime_val
        return mime_name

    if type_upper == "YOUTUBE_VIDEO":
        if not youtube_video_id:
            raise ToolError(
                "Error: 'youtube_video_id' is required when 'asset_type' is 'YOUTUBE_VIDEO'."
            )
        asset.youtube_video_asset.youtube_video_id = youtube_video_id
        return None

    if type_upper == "SITELINK":
        if not sitelink_link_text:
            raise ToolError(
                "Error: 'sitelink_link_text' is required when 'asset_type' is 'SITELINK'."
            )
        if not final_urls:
            raise ToolError(
                "Error: Root-level 'final_urls' is required when 'asset_type' is 'SITELINK'."
            )
        asset.sitelink_asset.link_text = sitelink_link_text
        if sitelink_description1:
            asset.sitelink_asset.description1 = sitelink_description1
        if sitelink_description2:
            asset.sitelink_asset.description2 = sitelink_description2
        return None

    if type_upper == "CALLOUT":
        if not callout_text:
            raise ToolError(
                "Error: 'callout_text' is required when 'asset_type' is 'CALLOUT'."
            )
        asset.callout_asset.callout_text = callout_text
        return None

    if type_upper == "STRUCTURED_SNIPPET":
        if not structured_snippet_header:
            raise ToolError(
                "Error: 'structured_snippet_header' is required when 'asset_type' is 'STRUCTURED_SNIPPET'."
            )
        if not structured_snippet_values:
            raise ToolError(
                "Error: 'structured_snippet_values' list is required when 'asset_type' is 'STRUCTURED_SNIPPET'."
            )
        asset.structured_snippet_asset.header = structured_snippet_header
        asset.structured_snippet_asset.values.extend(structured_snippet_values)
        return None

    return None


@assets_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
def create_asset(
    customer_id: str | int,
    asset_type: str,
    name: str | None = None,
    final_urls: list[str] | None = None,
    final_mobile_urls: list[str] | None = None,
    tracking_url_template: str | None = None,
    final_url_suffix: str | None = None,
    url_custom_parameters: list[UrlCustomParameter] | None = None,
    # Text Asset
    text_asset_text: str | None = None,
    # Image Asset
    image_asset_path: str | None = None,
    image_asset_data: str | None = None,
    image_asset_mime_type: str | None = None,
    # YouTube Video Asset
    youtube_video_id: str | None = None,
    # Sitelink Asset
    sitelink_link_text: str | None = None,
    sitelink_description1: str | None = None,
    sitelink_description2: str | None = None,
    # Callout Asset
    callout_text: str | None = None,
    # Structured Snippet Asset
    structured_snippet_header: str | None = None,
    structured_snippet_values: list[str] | None = None,
    # Fallback/Custom Parameters
    extra_params: dict[str, Any] | None = None,
    login_customer_id: str | int | None = None,
    validate_only: bool = True,
    checksum: str | None = None,
) -> str:
    """Creates a new Google Ads asset under the specified customer account.

    Required & Optional parameters per `asset_type`:
    - **TEXT**: Requires `text_asset_text`.
    - **IMAGE**: Requires either `image_asset_path` (absolute local path, local stdio mode only)
      OR `image_asset_data` (base64 encoded string). If `image_asset_data` is provided,
      `image_asset_mime_type` is also required (e.g. 'IMAGE_PNG', 'IMAGE_JPEG', 'IMAGE_GIF').
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

    For any other asset type, provide `extra_params` as a dict representing the sub-asset message fields.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `create_asset` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without committing changes.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `create_asset` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (digits or hyphenated, e.g. '1234567890').
        asset_type: Type of the asset (e.g., 'TEXT', 'IMAGE', 'YOUTUBE_VIDEO', 'SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET').
        name: Optional name of the asset.
        final_urls: Optional list of final URLs (required for SITELINK).
        final_mobile_urls: Optional list of final mobile URLs.
        tracking_url_template: Optional tracking URL template.
        final_url_suffix: Optional final URL suffix.
        url_custom_parameters: Optional custom parameters for tracking (list of {'key': ..., 'value': ...} dicts).
        text_asset_text: Optional text content (required for TEXT type).
        image_asset_path: Optional absolute file path to a local image (supported for IMAGE type in local stdio mode).
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
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without creating the asset. If False, requires `checksum` from a prior `validate_only=True` call to commit the asset creation.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.
    """
    cleaned_customer_id = utils.clean_customer_id(customer_id)
    if not cleaned_customer_id:
        raise ToolError("Error: 'customer_id' must contain digits.")

    ga_client = utils.get_googleads_client(login_customer_id=login_customer_id)
    asset_service = utils.get_googleads_service_from_client(
        ga_client, "AssetService"
    )

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
                raise ToolError(
                    "Error: Each item in 'url_custom_parameters' must contain non-empty 'key' and 'value'."
                )
            param = ga_client.get_type("CustomParameter")
            param.key = key
            param.value = value
            asset.url_custom_parameters.append(param)

    # Parse and validate AssetType
    asset_type_enum = ga_client.get_type("AssetTypeEnum").AssetType
    valid_types = {
        t.name: t
        for t in asset_type_enum
        if t.name not in ("UNSPECIFIED", "UNKNOWN")
    }
    type_upper = asset_type.upper()
    if type_upper not in valid_types:
        raise ToolError(
            f"Error: Invalid 'asset_type' value '{asset_type}'. "
            f"Must be one of: {', '.join(valid_types)}."
        )
    asset.type_ = valid_types[type_upper]

    if type_upper not in _DEDICATED_ASSET_TYPES and not extra_params:
        raise ToolError(
            f"Error: 'extra_params' is required when 'asset_type' is '{type_upper}'."
        )

    # 2. Populate Sub-Asset details
    resolved_mime_name = _populate_sub_asset(
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

    # 3. Fallback/Custom parameters populator
    if extra_params:
        field_name = f"{type_upper.lower()}_asset"
        if not hasattr(asset, field_name):
            raise ToolError(
                f"Error: Asset type field '{field_name}' does not exist on the Asset resource."
            )
        sub_msg = getattr(asset, field_name)
        try:
            ParseDict(extra_params, type(sub_msg).pb(sub_msg))
        except Exception as exc:
            raise ToolError(
                f"Error populating 'extra_params' for '{field_name}': {exc}"
            ) from exc

    # 4. Propose & Confirm workflow
    image_bytes = asset.image_asset.data if type_upper == "IMAGE" else None
    operation_payload = {
        "tool": "create_asset",
        "operation": utils.MutateOperation.CREATE.value,
        "asset_type": type_upper,
        "name": name,
        "final_urls": final_urls,
        "final_mobile_urls": final_mobile_urls,
        "tracking_url_template": tracking_url_template,
        "final_url_suffix": final_url_suffix,
        "url_custom_parameters": url_custom_parameters,
        "text_asset_text": text_asset_text,
        "image_asset_path": image_asset_path,
        "image_asset_data": image_asset_data,
        "image_asset_mime_type": resolved_mime_name,
        "image_bytes": image_bytes,
        "youtube_video_id": youtube_video_id,
        "sitelink_link_text": sitelink_link_text,
        "sitelink_description1": sitelink_description1,
        "sitelink_description2": sitelink_description2,
        "callout_text": callout_text,
        "structured_snippet_header": structured_snippet_header,
        "structured_snippet_values": structured_snippet_values,
        "extra_params": extra_params,
    }

    change_items = pac.build_change_items(
        operation=utils.MutateOperation.CREATE.value,
        entity_readable=f"Asset ({type_upper})",
        primary_key_readable=name or type_upper,
        fields={
            "Asset Type": type_upper,
            "Name": name,
            "Text": text_asset_text,
            "Image Path": image_asset_path,
            "Image MIME Type": resolved_mime_name,
            "Image Size (bytes)": (
                len(image_bytes) if image_bytes is not None else None
            ),
            "YouTube Video ID": youtube_video_id,
            "Sitelink Text": sitelink_link_text,
            "Sitelink Description 1": sitelink_description1,
            "Sitelink Description 2": sitelink_description2,
            "Callout Text": callout_text,
            "Structured Snippet Header": structured_snippet_header,
            "Structured Snippet Values": structured_snippet_values,
            "Final URLs": final_urls,
            "Final Mobile URLs": final_mobile_urls,
            "Tracking URL Template": tracking_url_template,
            "Final URL Suffix": final_url_suffix,
            "URL Custom Parameters": url_custom_parameters,
            "Extra Parameters": extra_params,
        },
    )

    request = ga_client.get_type("MutateAssetsRequest")
    request.customer_id = cleaned_customer_id
    request.operations.append(asset_op)
    request.validate_only = validate_only

    def _validate() -> None:
        request.validate_only = True
        asset_service.mutate_assets(request=request)

    def _commit() -> str:
        request.validate_only = False
        response = asset_service.mutate_assets(request=request)
        created_rn = response.results[0].resource_name
        created_id = utils.extract_id(created_rn)
        return f"Successfully created asset. ID: {created_id}"

    return pac.propose_and_confirm(
        customer_id=cleaned_customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=_validate,
        commit_fn=_commit,
        error_prefix="Failed to create asset",
    )
