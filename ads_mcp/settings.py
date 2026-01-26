import datetime as dt
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import (
    FastMCP,
)
from mcp.server.fastmcp.server import Settings as BaseFastMcpSettings
from mcp.server.lowlevel.server import LifespanResultT
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def create_settings_config(path: tuple[str, ...]) -> SettingsConfigDict:
    env_path = "_".join(path).lower() + "_"
    return SettingsConfigDict(
        env_prefix=env_path,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class FastMcpSettings(BaseFastMcpSettings):
    """
    FastMCP server settings. But with defaults to pass them to
    the FastMCP constructor.
    """

    # Server settings
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # HTTP settings
    host: str = "127.0.0.1"
    port: int = 8000
    mount_path: str = "/"
    sse_path: str = "/sse"
    message_path: str = "/messages/"
    streamable_http_path: str = "/mcp"

    # StreamableHTTP settings
    json_response: bool = False
    stateless_http: bool = False
    """Define if the server should create a new transport per request."""

    # resource settings
    warn_on_duplicate_resources: bool = True

    # tool settings
    warn_on_duplicate_tools: bool = True

    # prompt settings
    warn_on_duplicate_prompts: bool = True

    # TODO(Marcelo): Investigate if this is used. If it is, it's probably a good idea to remove it.
    dependencies: list[str] = Field(default_factory=list)
    """A list of dependencies to install in the server environment."""

    lifespan: (
        Callable[
            [FastMCP[LifespanResultT]],
            AbstractAsyncContextManager[LifespanResultT],
        ]
        | None
    ) = None
    """A async context manager that will be called when the server is started."""

    auth: AuthSettings | None = None

    # Transport security settings (DNS rebinding protection)
    transport_security: TransportSecuritySettings | None = None


class BasicAuthSettings(BaseSettings):
    model_config = create_settings_config(("basic", "auth"))

    username: str
    password: SecretStr


class BearerAuthSettings(BaseSettings):
    model_config = create_settings_config(("bearer", "auth"))

    token: SecretStr | None = None


class JwtProviderSettings(BaseSettings):
    model_config = create_settings_config(("jwt", "provider"))

    private_keys: list[dict[str, Any]]
    algorithm: str | None = None
    token_lifetime: dt.timedelta = dt.timedelta(minutes=1)
    claims: dict[str, Any] = Field(default_factory=dict)


class TokenVerifierSettings(BaseSettings):
    model_config = create_settings_config(("token", "verifier"))

    url: str = "https://www.googleapis.com/oauth2/v1/tokeninfo"
    auth: Literal["bearer", "basic", "none"] = "none"
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] = "GET"
    required_scopes: list[str] | None = None
    content_type: Literal[
        "application/json", "application/x-www-form-urlencoded"
    ] = "application/json"


class ServerSettings(BaseSettings):
    model_config = create_settings_config(("server",))

    transport: Literal["stdio", "streamable-http", "sse"] = "stdio"


class GoogleAdsSettings(BaseSettings):
    model_config = create_settings_config(("google", "ads"))

    client_id: str
    client_secret: SecretStr
    developer_token: str
    login_customer_id: str | None = None


google_ads_settings = GoogleAdsSettings()  # type: ignore[call-arg]
