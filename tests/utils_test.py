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

"""Test cases for the utils module."""

import unittest
from google.ads.googleads.v25.enums.types.campaign_status import (
    CampaignStatusEnum,
)
from google.ads.googleads.v25.common.types.metrics import Metrics

from ads_mcp import utils


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def test_format_output_value(self):
        """Tests that output values are formatted correctly."""

        self.assertEqual(
            utils.format_output_value(
                CampaignStatusEnum.CampaignStatus.ENABLED
            ),
            "ENABLED",
        )

    def test_get_googleads_service_uses_v25(self):
        """Requests the reviewed v25 service contract explicitly."""
        from unittest.mock import patch

        with patch("ads_mcp.utils._get_googleads_client") as mock_client:
            utils.get_googleads_service("CampaignService")

        _, kwargs = mock_client.return_value.get_service.call_args
        self.assertEqual(kwargs.get("version"), "v25")

    def test_get_googleads_type_uses_v25(self):
        """Requests the reviewed v25 message contract explicitly."""
        from unittest.mock import patch

        with patch("ads_mcp.utils._get_googleads_client") as mock_client:
            utils.get_googleads_type("SearchGoogleAdsRequest")

        mock_client.return_value.get_type.assert_called_once_with(
            "SearchGoogleAdsRequest", version="v25"
        )

    def test_format_output_value_primitive(self):
        """Tests that primitive values are returned as is."""
        self.assertEqual(utils.format_output_value(123), 123)
        self.assertEqual(utils.format_output_value("abc"), "abc")

    def test_format_output_value_message(self):
        """Tests that proto messages are converted to dict."""
        metrics = Metrics(clicks=10, impressions=100)
        formatted = utils.format_output_value(metrics)
        self.assertIsInstance(formatted, dict)
        self.assertEqual(formatted.get("clicks"), "10")
        self.assertEqual(formatted.get("impressions"), "100")

    def test_format_output_value_repeated_primitive(self):
        """Tests that repeated primitive values are formatted."""
        self.assertEqual(
            utils.format_output_value([1, 2, 3]),
            [1, 2, 3],
        )

    def test_format_output_value_repeated_message(self):
        """Tests that repeated proto messages are formatted."""
        metrics1 = Metrics(clicks=10)
        metrics2 = Metrics(clicks=20)
        formatted = utils.format_output_value([metrics1, metrics2])
        self.assertIsInstance(formatted, list)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0].get("clicks"), "10")
        self.assertEqual(formatted[1].get("clicks"), "20")

    def test_prevent_stdio_inheritance(self):
        """Tests that prevent_stdio_inheritance sets stdin to DEVNULL if not specified."""
        import subprocess
        from unittest.mock import MagicMock, patch
        from ads_mcp.utils import prevent_stdio_inheritance

        mock_popen = MagicMock()
        with patch("subprocess.Popen", mock_popen):
            with prevent_stdio_inheritance():
                subprocess.Popen(["mock_cmd"])

        mock_popen.assert_called_once_with(
            ["mock_cmd"], stdin=subprocess.DEVNULL
        )

    def test_prevent_stdio_inheritance_explicit_stdin(self):
        """Tests that prevent_stdio_inheritance preserves explicit stdin."""
        import subprocess
        from unittest.mock import MagicMock, patch
        from ads_mcp.utils import prevent_stdio_inheritance

        mock_popen = MagicMock()
        with patch("subprocess.Popen", mock_popen):
            with prevent_stdio_inheritance():
                subprocess.Popen(["mock_cmd"], stdin=subprocess.PIPE)

        mock_popen.assert_called_once_with(["mock_cmd"], stdin=subprocess.PIPE)
