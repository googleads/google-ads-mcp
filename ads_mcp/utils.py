#!/usr/bin/env python

# Copyright 2025 Google LLC.
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

"""Common utilities used by the MCP server."""

from typing import Any
import proto
import logging
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v23.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)

from google.ads.googleads.util import get_nested_attr
import google.auth
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
import os
import importlib.resources

# filename for generated field information used by search
_GAQL_FILENAME = "gaql_resources.json"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Google Ads API scope (read and write).
_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def _create_credentials() -> google.auth.credentials.Credentials:
    """Returns Application Default Credentials with Google Ads scope."""
    credentials, _ = google.auth.default(scopes=[_ADS_SCOPE])
    return credentials


def _get_developer_token() -> str:
    """Returns the developer token from the environment variable GOOGLE_ADS_DEVELOPER_TOKEN."""
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if dev_token is None:
        raise ValueError(
            "GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set."
        )
    return dev_token


def _get_login_customer_id() -> str | None:
    """Returns login customer id, if set, from the environment variable GOOGLE_ADS_LOGIN_CUSTOMER_ID."""
    return os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")


def _get_googleads_client(
    login_customer_id: str = None,
) -> GoogleAdsClient:
    args = {
        "credentials": _create_credentials(),
        "developer_token": _get_developer_token(),
    }

    # Use provided login_customer_id, fall back to env var.
    if not login_customer_id:
        login_customer_id = _get_login_customer_id()

    if login_customer_id:
        args["login_customer_id"] = login_customer_id

    client = GoogleAdsClient(**args)

    return client


# Lazy default client - initialized on first use to avoid
# crashing at import time when credentials are not available
_default_client = None


def _get_default_client():
    global _default_client
    if _default_client is None:
        _default_client = _get_googleads_client()
    return _default_client


def get_googleads_service(
    serviceName: str, login_customer_id: str = None
) -> GoogleAdsServiceClient:
    """Gets a Google Ads service client.

    Args:
        serviceName: The service name (e.g., "GoogleAdsService").
        login_customer_id: Optional manager account ID to use
            instead of the env var. Required when accessing a
            client account through a different manager account.
    """
    if login_customer_id:
        client = _get_googleads_client(login_customer_id)
    else:
        client = _get_default_client()

    return client.get_service(
        serviceName, interceptors=[MCPHeaderInterceptor()]
    )


def get_googleads_type(typeName: str):
    return _get_default_client().get_type(typeName)


def get_googleads_client(login_customer_id: str = None):
    if login_customer_id:
        return _get_googleads_client(login_customer_id)
    return _get_default_client()


def format_output_value(value: Any) -> Any:
    if isinstance(value, proto.Enum):
        return value.name
    else:
        return value


def format_output_row(row: proto.Message, attributes):
    return {
        attr: format_output_value(get_nested_attr(row, attr))
        for attr in attributes
    }


def get_gaql_resources_filepath():
    package_root = importlib.resources.files("ads_mcp")
    file_path = package_root.joinpath(_GAQL_FILENAME)
    return file_path


def create_field_mask(updated_message):
    """Creates a FieldMask by comparing the updated message against an empty/None state.

    Uses protobuf_helpers.field_mask to detect which fields have been set
    on the updated message, which is the pattern recommended by the
    Google Ads API documentation.

    Args:
        updated_message: The proto-plus message with fields set for update.
            Can be either a proto-plus wrapper or a raw protobuf message.

    Returns:
        A FieldMask protobuf message.
    """
    from google.api_core import protobuf_helpers

    # Handle both proto-plus wrapped messages and raw protobuf messages
    pb_message = getattr(updated_message, "_pb", updated_message)
    return protobuf_helpers.field_mask(None, pb_message)
