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

import grpc
import logging
from importlib import metadata

logger = logging.getLogger(__name__)


class MCPHeaderInterceptor(
    grpc.UnaryUnaryClientInterceptor, grpc.UnaryStreamClientInterceptor
):
    """A custom metadata interceptor to add the 'google-ads-mcp' header."""

    _API_CLIENT_HEADER = "x-goog-api-client"

    def _get_package_version_with_fallback():
        """Returns the version of the package.

        Falls back to 'unknown' if the version can't be resolved.
        """
        try:
            return metadata.version("google-ads-mcp")
        except:
            return "unknown"

    _MCP_EXTRA_HEADER = (
        f" google-ads-mcp/{_get_package_version_with_fallback()}"
    )

    def _mcp_intercept(self, continuation, client_call_details, request):
        """Generic interceptor used for Unary-Unary and Unary-Stream requests.

        Args:
            continuation: a function to continue the request process.
            client_call_details: a grpc._interceptor._ClientCallDetails
                instance containing request metadata.
            request: a SearchGoogleAdsRequest or SearchGoogleAdsStreamRequest
                message class instance.

        Returns:
            A grpc.Call/grpc.Future instance representing a service response.
        """
        try:
            if client_call_details.metadata is None:
                metadata = []
            else:
                metadata = list(client_call_details.metadata)

            for i, metadatum in enumerate(metadata):
                # Check if the user agent header key is in the current metadatum
                if metadatum[0] == self._API_CLIENT_HEADER:
                    # Convert the tuple to a list so it can be modified.
                    val = list(metadatum)
                    # Check that "google-ads-mcp" isn't already included in the user agent.
                    if "google-ads-mcp" not in val[1]:
                        # Append the protobuf version key value pair to the end of
                        # the string.
                        val[1] += self._MCP_EXTRA_HEADER
                        # Convert the metadatum back to a tuple and
                        # Splice it back in its original position in
                        # order to preserve the order of the metadata list.
                        metadata[i] = tuple(val)
                        # Exit the loop since we already found the user agent.
                        break

            new_client_call_details = client_call_details._replace(
                metadata=metadata
            )
            return continuation(new_client_call_details, request)
        except:
            logger.error("Error in MCPHeaderInterceptor", exc_info=True)
            return continuation(client_call_details, request)

    def intercept_unary_stream(
        self, continuation, client_call_details, request
    ):
        return self._mcp_intercept(continuation, client_call_details, request)

    def intercept_unary_unary(self, continuation, client_call_details, request):
        return self._mcp_intercept(continuation, client_call_details, request)
