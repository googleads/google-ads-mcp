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

import importlib.resources
import logging
import pathlib
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal, overload

import google.auth
import proto
from google.ads.googleads.client import GoogleAdsClient

# from google.ads.googleads import oauth2
from google.ads.googleads.util import get_nested_attr
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as OAuth2Credentials
from mcp.server.auth.middleware.auth_context import get_access_token

from ads_mcp.coordinator import mcp
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
from ads_mcp.settings import google_ads_settings

if TYPE_CHECKING:
    from google.ads.googleads.v22.services.services.customer_service import (
        CustomerServiceClient,
    )
    from google.ads.googleads.v22.services.services.google_ads_field_service import (
        GoogleAdsFieldServiceClient,
    )
    from google.ads.googleads.v22.services.services.google_ads_service import (
        GoogleAdsServiceClient,
    )
    from google.ads.googleads.v22.services.types.google_ads_field_service import (
        SearchGoogleAdsFieldsRequest,
    )
    from google.protobuf.message import Message as GoogleProtobufMessage
    from proto.message import Message as ProtoMessage


# filename for generated field information used by search
_GAQL_FILENAME = "gaql_resources.json"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Read-only scope for Analytics Admin API and Analytics Data API.
_READ_ONLY_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"

if mcp.settings.auth is not None:
    def _create_credentials() -> Credentials:
        access_token = get_access_token()
        assert access_token is not None, "Access token is required but not found in context."
        credentials = OAuth2Credentials(
            client_id=google_ads_settings.client_id,
            client_secret=google_ads_settings.client_secret.get_secret_value(),
            token=access_token.token
        )
        return credentials

else:
    def _create_credentials() -> Credentials:
        """Returns Application Default Credentials with read-only scope."""
        (credentials, _) = google.auth.default(scopes=[_READ_ONLY_ADS_SCOPE])
        return credentials



def _get_developer_token() -> str:
    """Returns the developer token from the environment variable GOOGLE_ADS_DEVELOPER_TOKEN."""
    return google_ads_settings.developer_token


def _get_login_customer_id() -> str | None:
    """Returns login customer id, if set, from the environment variable GOOGLE_ADS_LOGIN_CUSTOMER_ID."""
    return google_ads_settings.login_customer_id



def _get_googleads_client() -> GoogleAdsClient:
    # Use this line if you have a google-ads.yaml file
    # client = GoogleAdsClient.load_from_storage()
    # GoogleAdsClient.load_from_storage()
    client = GoogleAdsClient(
        developer_token=_get_developer_token(),
        login_customer_id=_get_login_customer_id(),
        credentials=_create_credentials(),  # type: ignore[arg-type]
        version="v22",
    )

    return client


@overload
def get_googleads_service(
    service_name: Literal["GoogleAdsService"]
) -> "GoogleAdsServiceClient": ...


@overload
def get_googleads_service(
    service_name: Literal["GoogleAdsFieldService"]
) -> "GoogleAdsFieldServiceClient": ...


@overload
def get_googleads_service(
    service_name: Literal["CustomerService"]
) -> "CustomerServiceClient": ...


@overload
def get_googleads_service(
    service_name: str
) -> Any: ...


def get_googleads_service(
    service_name: str
) -> Any:
    return _get_googleads_client().get_service(
        service_name, interceptors=[MCPHeaderInterceptor()]
    )


@overload
def get_googleads_type(
    type_name: Literal["SearchGoogleAdsFieldsRequest"],
) -> "SearchGoogleAdsFieldsRequest": ...


@overload
def get_googleads_type(
    type_name: str
) -> "ProtoMessage | GoogleProtobufMessage": ...


def get_googleads_type(
    type_name: str
) -> "ProtoMessage | GoogleProtobufMessage":
    return _get_googleads_client().get_type(type_name)


def format_output_value(value: Any) -> Any:
    if isinstance(value, proto.Enum):
        return value.name
    else:
        return value


def format_output_row(
    row: proto.Message, attributes: Iterable[Any]
) -> dict[str, Any]:
    return {
        attr: format_output_value(get_nested_attr(row, attr))
        for attr in attributes
    }


def get_gaql_resources_filepath() -> pathlib.Path:
    package_root = importlib.resources.files("ads_mcp")
    file_path = package_root.joinpath(_GAQL_FILENAME)
    return file_path  # type: ignore[return-value]
