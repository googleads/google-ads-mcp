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

import os
import unittest
from unittest.mock import patch

from google.ads.googleads.v25.enums.types.campaign_status import (
    CampaignStatusEnum,
)
from google.ads.googleads.v25.common.types.metrics import Metrics
from google.protobuf.field_mask_pb2 import FieldMask

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

    def test_format_output_value_bare_protobuf(self):
        """Tests that bare protobuf messages are formatted correctly."""
        fm = FieldMask(paths=["foo", "bar"])
        formatted = utils.format_output_value(fm)
        self.assertEqual(formatted, "foo,bar")

    def test_get_login_customer_id_prefers_argument(self):
        """Tests that an explicit login customer id wins over the env var."""
        with patch.dict(
            os.environ, {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "1111111111"}
        ):
            self.assertEqual(
                utils._get_login_customer_id("2222222222"), "2222222222"
            )

    def test_get_login_customer_id_falls_back_to_environment(self):
        """Tests that the env var is used when no id is passed in."""
        with patch.dict(
            os.environ, {"GOOGLE_ADS_LOGIN_CUSTOMER_ID": "1111111111"}
        ):
            self.assertEqual(utils._get_login_customer_id(), "1111111111")

    def test_get_login_customer_id_unset(self):
        """Tests that None is returned when neither source is set."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(utils._get_login_customer_id())

    @patch("ads_mcp.utils._get_developer_token", return_value="token")
    @patch("ads_mcp.utils._create_credentials", return_value="credentials")
    @patch("ads_mcp.utils.GoogleAdsClient")
    def test_get_googleads_client_with_login_customer_id(
        self, mock_client, mock_credentials, mock_token
    ):
        """Tests that the requested login customer id reaches the client."""
        with patch.dict(os.environ, {}, clear=True):
            utils._get_googleads_client("2222222222")

        mock_client.assert_called_once_with(
            credentials="credentials",
            developer_token="token",
            use_proto_plus=True,
            login_customer_id="2222222222",
        )

    @patch("ads_mcp.utils._get_developer_token", return_value="token")
    @patch("ads_mcp.utils._create_credentials", return_value="credentials")
    @patch("ads_mcp.utils.GoogleAdsClient")
    def test_get_googleads_client_without_login_customer_id(
        self, mock_client, mock_credentials, mock_token
    ):
        """Tests that no login customer id is set when none is available."""
        with patch.dict(os.environ, {}, clear=True):
            utils._get_googleads_client()

        mock_client.assert_called_once_with(
            credentials="credentials",
            developer_token="token",
            use_proto_plus=True,
        )

    @patch("ads_mcp.utils._get_googleads_client")
    def test_get_googleads_service_passes_login_customer_id(
        self, mock_get_client
    ):
        """Tests that get_googleads_service forwards the login customer id."""
        utils.get_googleads_service(
            "GoogleAdsService", login_customer_id="2222222222"
        )

        mock_get_client.assert_called_once_with("2222222222")

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
