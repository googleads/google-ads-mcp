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

"""Tests for the segments resource."""

import unittest
import urllib.request
from unittest import mock

from ads_mcp.resources import segments


class SegmentsTest(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_get_segments(self, mock_urlopen):
        # Setup mock response
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b"Mock segments content"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        # Call function
        result = segments.get_segments()

        # Assertions
        self.assertEqual(result, "Mock segments content")

        # Verify urlopen was called correctly
        mock_urlopen.assert_called_once()
        args, _ = mock_urlopen.call_args
        request_obj = args[0]

        self.assertIsInstance(request_obj, urllib.request.Request)
        self.assertEqual(
            request_obj.full_url,
            "https://developers.google.com/google-ads/api/fields/latest/segments",
        )
        self.assertEqual(request_obj.headers.get("User-agent"), "Mozilla/5.0")
