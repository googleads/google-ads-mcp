#!/usr/bin/env python

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

"""Common utilities used by the MCP server."""

from enum import Enum
from typing import Any
import proto
from google.protobuf.message import Message as PbMessage
from google.protobuf.json_format import MessageToDict
import logging
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.v25.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)

from google.ads.googleads.util import get_nested_attr
import google.auth
from google.oauth2 import service_account
from fastmcp.exceptions import ToolError
import json
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
import os
import re
import importlib.resources
import contextlib
import subprocess
from unittest.mock import patch

# filename for generated field information used by search
_GAQL_FILENAME = "gaql_resources.txt"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# OAuth scope for the Google Ads API. Google Ads does not publish a separate
# read-only scope; exposed mutation tools require propose-and-confirm.
_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


class MutateOperation(str, Enum):
    """Common Google Ads mutation operations."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


def is_remote_oauth_mode() -> bool:
    """Returns whether the server is running with hosted OAuth credentials."""
    return bool(
        os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
        and os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    )


def format_google_ads_error(ex: GoogleAdsException) -> str:
    """Formats a Google Ads API error consistently across all tools."""
    details = "\n".join(
        f"Google Ads API Error: {error.message}" for error in ex.failure.errors
    )
    return f"Request ID: {ex.request_id}" + (f"\n{details}" if details else "")


@contextlib.contextmanager
def prevent_stdio_inheritance():
    """Prevents child processes from inheriting the parent's stdio handles.

    Fixes a deadlock on Windows where `google.auth.default()` spawns `gcloud`
    via subprocess without redirecting stdin, causing it to inherit the
    ProactorEventLoop's overlapping I/O handles used by MCP's stdio transport.
    """
    original_popen = subprocess.Popen

    def safe_popen(*args, **kwargs):
        if kwargs.get("stdin") is None:
            kwargs["stdin"] = subprocess.DEVNULL
        return original_popen(*args, **kwargs)

    with patch("subprocess.Popen", new=safe_popen):
        yield


def _mcp_oauth_enabled() -> bool:
    """Returns True when the server runs FastMCP's Google OAuth login.

    Mirrors the condition in ads_mcp/coordinator.py that installs the
    GoogleProvider. Without it there is no user token to look up.
    """
    return bool(
        os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
        and os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    )


def _adc_enabled() -> bool:
    """Returns True when Application Default Credentials are explicitly allowed.

    ADC is opt-in (GOOGLE_ADS_MCP_ALLOW_ADC=true) so a hosted server never
    falls back to a login method it was not configured with.
    """
    return os.environ.get("GOOGLE_ADS_MCP_ALLOW_ADC", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _refresh_token_credentials(
    refresh_token: str, client_id: str, client_secret: str
) -> google.auth.credentials.Credentials:
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[_ADS_SCOPE],
    )


def _create_credentials() -> google.auth.credentials.Credentials:
    """Returns credentials for calls made without an account_name.

    Only configured methods are tried, in this order:
      1. The FastMCP OAuth user token, when MCP OAuth login is enabled.
      2. GOOGLE_ADS_REFRESH_TOKEN with the OAuth client ID and secret.
      3. Application Default Credentials, when GOOGLE_ADS_MCP_ALLOW_ADC is set.
    """
    if _mcp_oauth_enabled():
        from fastmcp.server.dependencies import get_access_token

        token_obj = get_access_token()
        if token_obj and token_obj.token:
            from google.oauth2.credentials import Credentials

            return Credentials(token=token_obj.token)

    refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    if refresh_token and client_id and client_secret:
        return _refresh_token_credentials(
            refresh_token, client_id, client_secret
        )

    if _adc_enabled():
        with prevent_stdio_inheritance():
            credentials, _ = google.auth.default(scopes=[_ADS_SCOPE])
        return credentials

    accounts = [a.get("name") for a in _get_account_configs()]
    raise ToolError(
        "No default Google Ads credentials are configured on this server. "
        + (
            f"Pass account_name, one of: {accounts}."
            if accounts
            else "Set GOOGLE_ADS_ACCOUNTS_CONFIG or GOOGLE_ADS_REFRESH_TOKEN."
        )
    )


def _get_developer_token() -> str | None:
    """Returns the developer token from the environment variable GOOGLE_ADS_DEVELOPER_TOKEN, if set."""
    return os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")


def clean_customer_id(customer_id: str | int) -> str:
    """Cleans a customer ID by stripping non-digit characters."""
    return re.sub(r"\D", "", str(customer_id))


def _get_login_customer_id(
    login_customer_id: str | int | None = None,
) -> str | None:
    """Returns login customer id, if set, from the parameter or the environment variable GOOGLE_ADS_LOGIN_CUSTOMER_ID."""
    resolved_login_customer_id = (
        login_customer_id
        if login_customer_id is not None
        else os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    )
    if resolved_login_customer_id:
        return clean_customer_id(resolved_login_customer_id)
    return None


# ---------------------------------------------------------------------------
# Multi-account support
# ---------------------------------------------------------------------------


def _get_account_configs() -> list:
    """Returns the account configs from the GOOGLE_ADS_ACCOUNTS_CONFIG env var.

    JSON array, one object per account:
    [
      {
        "name": "account_a",
        "developer_token": "TOKEN_A",
        "login_customer_id": "1234567890",
        "refresh_token": "...", "client_id": "...", "client_secret": "..."
      }
    ]
    Instead of refresh_token/client_id/client_secret an account may set
    credentials_json (a service account JSON string or object).
    """
    raw = os.environ.get("GOOGLE_ADS_ACCOUNTS_CONFIG")
    return json.loads(raw) if raw else []


def _get_account_config(account_name: str) -> dict:
    accounts = _get_account_configs()
    account = next((a for a in accounts if a.get("name") == account_name), None)
    if account is None:
        raise ToolError(
            f"Account '{account_name}' not found in GOOGLE_ADS_ACCOUNTS_CONFIG. "
            f"Available accounts: {[a.get('name') for a in accounts]}"
        )
    return account


def _create_credentials_for_account(
    account_config: dict,
) -> google.auth.credentials.Credentials:
    """Returns credentials from the account config only.

    Uses the account's refresh token (with client_id and client_secret), or
    its service account JSON. No other login method is tried.
    """
    refresh_token = account_config.get("refresh_token")
    client_id = account_config.get("client_id")
    client_secret = account_config.get("client_secret")
    if refresh_token and client_id and client_secret:
        return _refresh_token_credentials(
            refresh_token, client_id, client_secret
        )

    creds_json = account_config.get("credentials_json")
    if creds_json:
        info = (
            json.loads(creds_json)
            if isinstance(creds_json, str)
            else creds_json
        )
        return service_account.Credentials.from_service_account_info(
            info, scopes=[_ADS_SCOPE]
        )

    raise ToolError(
        f"Account '{account_config.get('name')}' has no credentials. Set "
        "refresh_token, client_id and client_secret, or credentials_json."
    )


def _get_googleads_client(
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> GoogleAdsClient:
    """Builds a GoogleAdsClient.

    With account_name, credentials, developer token and login customer ID come
    from that entry in GOOGLE_ADS_ACCOUNTS_CONFIG. login_customer_id, when
    passed, overrides the account's value.
    """
    if account_name:
        account = _get_account_config(account_name)
        dev_token = account.get("developer_token")
        if not dev_token:
            raise ToolError(
                f"Account '{account_name}' is missing 'developer_token'."
            )
        args = {
            "credentials": _create_credentials_for_account(account),
            "developer_token": dev_token,
            "use_proto_plus": True,
        }
        resolved_login_customer_id = _get_login_customer_id(
            login_customer_id
            if login_customer_id is not None
            else account.get("login_customer_id")
        )
        if resolved_login_customer_id:
            args["login_customer_id"] = resolved_login_customer_id
        return GoogleAdsClient(**args)

    args = {
        "credentials": _create_credentials(),
        "use_proto_plus": True,
    }

    # If the developer-token is not set, avoid setting None.
    dev_token = _get_developer_token()
    if dev_token:
        args["developer_token"] = dev_token

    # If the login-customer-id is not set, avoid setting None.
    resolved_login_customer_id = _get_login_customer_id(login_customer_id)

    if resolved_login_customer_id:
        args["login_customer_id"] = resolved_login_customer_id

    return GoogleAdsClient(**args)


def get_googleads_service(
    serviceName: str,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> GoogleAdsServiceClient:
    return get_googleads_service_from_client(
        _get_googleads_client(
            login_customer_id=login_customer_id, account_name=account_name
        ),
        serviceName,
    )


def get_googleads_service_from_client(
    client: GoogleAdsClient, service_name: str
) -> Any:
    """Gets a service from an existing account-scoped client with MCP telemetry."""
    return client.get_service(
        service_name, interceptors=[MCPHeaderInterceptor()]
    )


def get_googleads_type(typeName: str, account_name: str | None = None):
    return _get_googleads_client(account_name=account_name).get_type(typeName)


def get_googleads_client(
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> GoogleAdsClient:
    return _get_googleads_client(
        login_customer_id=login_customer_id, account_name=account_name
    )


def format_output_value(value: Any) -> Any:
    if isinstance(value, proto.Enum):
        return value.name
    elif isinstance(value, proto.Message):
        return proto.Message.to_dict(value)
    elif isinstance(value, PbMessage):
        return MessageToDict(value, preserving_proto_field_name=True)
    elif hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        return [format_output_value(v) for v in value]
    else:
        return value


def format_output_row(row: proto.Message, attributes):
    return {
        attr: format_output_value(get_nested_attr(row, attr))
        for attr in attributes
    }


def extract_id(resource_name_or_id: str) -> str:
    """Returns a resource ID from a Google Ads resource name or a raw ID."""
    return resource_name_or_id.rsplit("/", maxsplit=1)[-1]


def get_gaql_resources_filepath():
    package_root = importlib.resources.files("ads_mcp")
    file_path = package_root.joinpath(_GAQL_FILENAME)
    return file_path
