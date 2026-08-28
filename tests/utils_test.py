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

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
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


class TestSubjectDelegation(unittest.TestCase):
    """Test cases for service account subject delegation."""

    def _write_credentials_file(self, contents):
        """Writes contents to a temporary file and returns its path."""
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.addCleanup(os.unlink, handle.name)
        with handle:
            handle.write(contents)
        return handle.name

    def test_no_subject_returns_none(self):
        """Tests that delegation is skipped when no subject is set."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(utils._create_delegated_credentials())

    def test_no_credentials_file_returns_none(self):
        """Tests that delegation is skipped without a credentials file."""
        env = {"GOOGLE_ADS_SUBJECT": "user@example.com"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(utils._create_delegated_credentials())

    def test_oauth_credentials_returns_none(self):
        """Tests that delegation is skipped for non service account keys."""
        path = self._write_credentials_file(
            json.dumps({"type": "authorized_user"})
        )
        env = {
            "GOOGLE_ADS_SUBJECT": "user@example.com",
            "GOOGLE_APPLICATION_CREDENTIALS": path,
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(utils._create_delegated_credentials())

    def test_unreadable_credentials_file_returns_none(self):
        """Tests that an unreadable credentials file is not fatal."""
        env = {
            "GOOGLE_ADS_SUBJECT": "user@example.com",
            "GOOGLE_APPLICATION_CREDENTIALS": "/does/not/exist.json",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(utils._create_delegated_credentials())

    def test_malformed_credentials_file_returns_none(self):
        """Tests that a credentials file with invalid JSON is not fatal."""
        path = self._write_credentials_file("not json")
        env = {
            "GOOGLE_ADS_SUBJECT": "user@example.com",
            "GOOGLE_APPLICATION_CREDENTIALS": path,
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertIsNone(utils._create_delegated_credentials())

    def test_service_account_applies_subject(self):
        """Tests that the subject is applied to service account keys."""
        credentials_info = {
            "type": "service_account",
            "client_email": "sa@example.iam.gserviceaccount.com",
        }
        path = self._write_credentials_file(json.dumps(credentials_info))
        env = {
            "GOOGLE_ADS_SUBJECT": "user@example.com",
            "GOOGLE_APPLICATION_CREDENTIALS": path,
        }
        mock_credentials = MagicMock()
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(
                utils.service_account.Credentials,
                "from_service_account_info",
                return_value=mock_credentials,
            ) as mock_from_info,
        ):
            delegated = utils._create_delegated_credentials()

        mock_from_info.assert_called_once_with(
            credentials_info, scopes=[utils._ADS_SCOPE]
        )
        mock_credentials.with_subject.assert_called_once_with(
            "user@example.com"
        )
        self.assertEqual(delegated, mock_credentials.with_subject.return_value)

    def test_create_credentials_prefers_delegation_over_adc(self):
        """Tests that delegated credentials take precedence over ADC."""
        mock_credentials = MagicMock()
        with (
            patch(
                "fastmcp.server.dependencies.get_access_token",
                return_value=None,
            ),
            patch.object(
                utils,
                "_create_delegated_credentials",
                return_value=mock_credentials,
            ),
            patch.object(utils.google.auth, "default") as mock_default,
        ):
            self.assertEqual(utils._create_credentials(), mock_credentials)

        mock_default.assert_not_called()

    def test_create_credentials_prefers_token_over_delegation(self):
        """Tests that the FastMCP token takes precedence over delegation."""
        token = MagicMock(token="an-access-token")
        with (
            patch(
                "fastmcp.server.dependencies.get_access_token",
                return_value=token,
            ),
            patch.object(
                utils, "_create_delegated_credentials"
            ) as mock_delegated,
        ):
            credentials = utils._create_credentials()

        self.assertEqual(credentials.token, "an-access-token")
        mock_delegated.assert_not_called()
