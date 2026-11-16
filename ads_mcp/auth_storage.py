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

"""Storage creation utilities for FastMCP OAuth state and MCP tool audit records."""

from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue

_CLIENT_STORAGE_SALT = "fastmcp-storage-encryption-key"
_AUDIT_STORAGE_SALT = "fastmcp-audit-storage-encryption-key"


def _create_kv_storage(
    env_prefix: str = "GOOGLE_ADS_MCP_STORAGE",
    label: str = "client",
    *,
    allow_oauth_secret_fallback: bool = True,
    encryption_salt: str = _CLIENT_STORAGE_SALT,
) -> AsyncKeyValue | None:
    """Creates an AsyncKeyValue store based on environment variables with the given prefix."""
    type_var = f"{env_prefix}_TYPE"
    path_var = f"{env_prefix}_PATH"
    redis_var = f"{env_prefix}_REDIS_URL"
    fs_project_var = f"{env_prefix}_FIRESTORE_PROJECT"
    fs_db_var = f"{env_prefix}_FIRESTORE_DATABASE"
    dis_enc_var = f"{env_prefix}_DISABLE_ENCRYPTION"
    enc_key_var = f"{env_prefix}_ENCRYPTION_KEY"

    st_type = os.environ.get(type_var)
    st_path = os.environ.get(path_var)
    r_url = os.environ.get(redis_var)
    fs_project = os.environ.get(fs_project_var)
    fs_database = os.environ.get(fs_db_var)

    if not st_type:
        if r_url:
            st_type = "redis"
        elif fs_project or fs_database:
            st_type = "firestore"
        elif st_path:
            st_type = "filetree"
        else:
            return None

    st_type = st_type.strip().lower()
    store: Any

    if st_type in ("filetree", "file", "dir", "path"):
        if not st_path:
            raise ValueError(
                f"Storage path must be provided via {path_var} environment "
                "variable."
            )
        from key_value.aio.stores.filetree import (
            FileTreeStore,
            FileTreeV1KeySanitizationStrategy,
        )

        path_obj = pathlib.Path(st_path)
        path_obj.mkdir(parents=True, exist_ok=True)
        store = FileTreeStore(
            data_directory=path_obj,
            key_sanitization_strategy=(
                FileTreeV1KeySanitizationStrategy(path_obj)
            ),
        )
    elif st_type == "redis":
        from key_value.aio.stores.redis import RedisStore

        url_to_use = r_url or "redis://localhost:6379/0"
        store = RedisStore(url=url_to_use)
    elif st_type == "firestore":
        try:
            from key_value.aio.stores.firestore import (
                FirestoreStore,
                FirestoreV1CollectionSanitizationStrategy,
                FirestoreV1KeySanitizationStrategy,
            )
        except ImportError as exc:
            raise ValueError(
                "Firestore storage requires the firestore extra. Install it "
                "with 'pip install py-key-value-aio[firestore]'."
            ) from exc

        from google.auth.exceptions import DefaultCredentialsError

        # Both project and database are optional: when omitted, the store falls
        # back to Application Default Credentials and the '(default)' database,
        # which is what a Cloud Run deployment normally wants.
        # The sanitization strategies are needed because CIMD client ids are
        # URLs, and Firestore rejects the '/' they contain in a document id.
        try:
            store = FirestoreStore(
                project=fs_project,
                database=fs_database,
                key_sanitization_strategy=(
                    FirestoreV1KeySanitizationStrategy()
                ),
                collection_sanitization_strategy=(
                    FirestoreV1CollectionSanitizationStrategy()
                ),
            )
        except DefaultCredentialsError as exc:
            raise ValueError(
                "Firestore storage could not resolve Application Default "
                "Credentials. Configure ADC for this environment, or set "
                f"{type_var} to a different backend."
            ) from exc
    elif st_type == "memory":
        from key_value.aio.stores.memory import MemoryStore

        store = MemoryStore()
    else:
        raise ValueError(
            f"Unsupported {label} storage type: '{st_type}'. Expected one of: "
            "filetree, redis, firestore, memory."
        )

    dis_enc = os.environ.get(dis_enc_var, "").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    if dis_enc:
        return store

    enc_key = os.environ.get(enc_key_var)
    secret_mat: str | None = None
    if not enc_key and allow_oauth_secret_fallback:
        jwt_signing_key = os.environ.get("GOOGLE_ADS_MCP_JWT_SIGNING_KEY")
        client_secret = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
        secret_mat = jwt_signing_key or client_secret

    if not enc_key and not secret_mat:
        return store

    from cryptography.fernet import Fernet
    from fastmcp.server.auth.oauth_proxy.proxy import derive_jwt_key
    from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper

    if enc_key:
        try:
            fernet = Fernet(enc_key.encode())
        except (ValueError, TypeError):
            derived_bytes = derive_jwt_key(
                high_entropy_material=enc_key,
                salt=encryption_salt,
            )
            fernet = Fernet(derived_bytes)
    else:
        assert secret_mat is not None
        derived_bytes = derive_jwt_key(
            high_entropy_material=secret_mat,
            salt=encryption_salt,
        )
        fernet = Fernet(derived_bytes)

    return FernetEncryptionWrapper(
        key_value=store,
        fernet=fernet,
        raise_on_decryption_error=False,
    )


def create_client_storage() -> AsyncKeyValue | None:
    """Creates an AsyncKeyValue store for FastMCP client_storage based on environment variables.

    Supports 'filetree', 'redis', 'firestore', and 'memory' storage backends.
    If no storage configuration is provided, returns None to allow FastMCP to use its
    default storage logic.
    """
    return _create_kv_storage(
        env_prefix="GOOGLE_ADS_MCP_STORAGE",
        label="client",
        allow_oauth_secret_fallback=True,
        encryption_salt=_CLIENT_STORAGE_SALT,
    )


def create_audit_storage() -> AsyncKeyValue | None:
    """Creates an optional AsyncKeyValue store for audit records based on environment variables.

    Configured via GOOGLE_ADS_MCP_AUDIT_STORAGE_* environment variables.
    Supports 'filetree', 'redis', 'firestore', and 'memory' storage backends.
    Audit records are stored as redacted JSON by default so backends like Firestore
    remain queryable and survive OAuth secret rotation; set
    GOOGLE_ADS_MCP_AUDIT_STORAGE_ENCRYPTION_KEY to enable Fernet encryption with a
    dedicated HKDF salt isolated from OAuth token storage.
    Returns None when not configured (log-only mode).
    """
    return _create_kv_storage(
        env_prefix="GOOGLE_ADS_MCP_AUDIT_STORAGE",
        label="audit",
        allow_oauth_secret_fallback=False,
        encryption_salt=_AUDIT_STORAGE_SALT,
    )


def get_audit_storage_ttl() -> float | None:
    """Returns optional TTL in seconds from GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS."""
    raw_ttl = os.environ.get("GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS")
    if raw_ttl is None or not raw_ttl.strip():
        return None
    try:
        ttl = float(raw_ttl.strip())
    except ValueError as exc:
        raise ValueError(
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS must be a positive number "
            f"of seconds, got {raw_ttl!r}."
        ) from exc
    if ttl <= 0:
        raise ValueError(
            "GOOGLE_ADS_MCP_AUDIT_STORAGE_TTL_SECONDS must be greater than 0, "
            f"got {raw_ttl!r}."
        )
    return ttl
