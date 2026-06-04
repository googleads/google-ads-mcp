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

"""Environment-gated feature flags for optional MCP tools."""

import os

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    """Returns whether an environment variable is set to a truthy value.

    Args:
        name: The environment variable name.

    Returns:
        True if the value is one of 1, true, yes, or on (case insensitive).
    """
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def is_mutate_enabled() -> bool:
    """Checks whether write tools are enabled.

    Returns:
        True if GOOGLE_ADS_MCP_ENABLE_MUTATE is set to a truthy value.
    """
    return _env_truthy("GOOGLE_ADS_MCP_ENABLE_MUTATE")


def is_remove_enabled() -> bool:
    """Checks whether the remove tool is enabled.

    Returns:
        True if mutate is enabled and GOOGLE_ADS_MCP_ENABLE_REMOVE is truthy.
    """
    return is_mutate_enabled() and _env_truthy("GOOGLE_ADS_MCP_ENABLE_REMOVE")


def mutate_chunk_size() -> int:
    """Returns the maximum number of operations per mutate request.

    Returns:
        A positive integer from GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE, default 500.

    Raises:
        ValueError: If the environment variable is not a positive integer.
    """
    raw = os.environ.get("GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE", "500")
    try:
        size = int(raw)
    except ValueError as ex:
        raise ValueError(
            "GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE must be a positive integer."
        ) from ex
    if size < 1:
        raise ValueError(
            "GOOGLE_ADS_MCP_MUTATE_CHUNK_SIZE must be a positive integer."
        )
    return size
