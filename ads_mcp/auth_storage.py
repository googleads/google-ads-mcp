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

"""Module providing storage creation utilities for FastMCP OAuth proxy authentication."""

import os
import pathlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from key_value.aio.protocols import AsyncKeyValue


def create_client_storage() -> Any:
    """Creates an AsyncKeyValue store for FastMCP client_storage based on environment variables.

    Supports 'filetree', 'redis', 'firestore', and 'memory' storage backends.
    If no storage configuration is provided, returns None to allow FastMCP to use its
    default storage logic.
    """
    st_type = os.environ.get("GOOGLE_ADS_MCP_STORAGE_TYPE")
    st_path = os.environ.get("GOOGLE_ADS_MCP_STORAGE_PATH")
    r_url = os.environ.get("GOOGLE_ADS_MCP_STORAGE_REDIS_URL")
    fs_project = os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_PROJECT")
    fs_database = os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_DATABASE")

    if not st_type:
        if r_url:
            st_type = "redis"
        elif fs_project or fs_database:
            st_type = "firestore"
        elif st_path:
            st_type = "filetree"
        else:
            return None

    st_type = st_type.lower()
    store: Any

    if st_type in ("filetree", "file", "dir", "path"):
        if not st_path:
            raise ValueError(
                "Storage path must be provided via GOOGLE_ADS_MCP_STORAGE_PATH environment variable."
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
                "GOOGLE_ADS_MCP_STORAGE_TYPE to a different backend."
            ) from exc
    elif st_type == "memory":
        from key_value.aio.stores.memory import MemoryStore

        store = MemoryStore()
    else:
        raise ValueError(
            f"Unsupported client storage type: '{st_type}'. Expected one of: filetree, redis, firestore, memory."
        )

    dis_enc = os.environ.get(
        "GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION", ""
    ).lower() in ("true", "1", "yes")

    if dis_enc:
        return store

    enc_key = os.environ.get("GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY")

    from cryptography.fernet import Fernet
    from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper
    from fastmcp.server.auth.oauth_proxy.proxy import derive_jwt_key

    fernet: Fernet | None = None
    if enc_key:
        try:
            fernet = Fernet(
                enc_key.encode() if isinstance(enc_key, str) else enc_key
            )
        except Exception:
            derived_bytes = derive_jwt_key(
                high_entropy_material=enc_key,
                salt="fastmcp-storage-encryption-key",
            )
            fernet = Fernet(derived_bytes)
    else:
        jwt_signing_key = os.environ.get("GOOGLE_ADS_MCP_JWT_SIGNING_KEY")
        client_secret = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
        secret_mat = jwt_signing_key or client_secret
        if secret_mat:
            derived_bytes = derive_jwt_key(
                high_entropy_material=secret_mat,
                salt="fastmcp-storage-encryption-key",
            )
            fernet = Fernet(derived_bytes)

    if fernet:
        return FernetEncryptionWrapper(
            key_value=store,
            fernet=fernet,
            raise_on_decryption_error=False,
        )
    return store
