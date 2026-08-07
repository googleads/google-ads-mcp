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

    Supports 'filetree', 'redis', and 'memory' storage backends.
    If no storage configuration is provided, returns None to allow FastMCP to use its
    default storage logic.
    """
    st_type = os.environ.get("GOOGLE_ADS_MCP_STORAGE_TYPE")
    st_path = os.environ.get("GOOGLE_ADS_MCP_STORAGE_PATH")
    r_url = os.environ.get("GOOGLE_ADS_MCP_STORAGE_REDIS_URL")

    if not st_type:
        if r_url:
            st_type = "redis"
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
        from key_value.aio.stores.filetree import FileTreeStore

        path_obj = pathlib.Path(st_path)
        path_obj.mkdir(parents=True, exist_ok=True)
        store = FileTreeStore(data_directory=path_obj)
    elif st_type == "redis":
        from key_value.aio.stores.redis import RedisStore

        url_to_use = r_url or "redis://localhost:6379/0"
        store = RedisStore(url=url_to_use)
    elif st_type == "memory":
        from key_value.aio.stores.memory import MemoryStore

        store = MemoryStore()
    else:
        raise ValueError(
            f"Unsupported client storage type: '{st_type}'. Expected one of: filetree, redis, memory."
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
