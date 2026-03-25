# Copyright 2025 Google LLC.
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
from google.ads.googleads.v23.common.types.metrics import Metrics
from google.ads.googleads.v23.enums.types.campaign_status import (
    CampaignStatusEnum,
)

from ads_mcp import utils


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def test_format_output_value(self):
        """Tests that output values are formatted correctly."""

        self.assertEqual(
            utils.format_output_value(CampaignStatusEnum.CampaignStatus.ENABLED),
            "ENABLED",
        )

    def test_format_output_value_proto_message(self):
        """Tests that proto.Message values are converted to dict."""

        msg = Metrics(clicks=100, impressions=1000)
        result = utils.format_output_value(msg)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["clicks"], "100")
        self.assertEqual(result["impressions"], "1000")

    def test_format_output_value_list(self):
        """Tests that list values are recursively formatted."""

        result = utils.format_output_value([1, "hello", 3.14])
        self.assertEqual(result, [1, "hello", 3.14])

    def test_format_output_value_list_with_enums(self):
        """Tests that lists containing enums are recursively formatted."""

        result = utils.format_output_value(
            [
                CampaignStatusEnum.CampaignStatus.ENABLED,
                CampaignStatusEnum.CampaignStatus.PAUSED,
            ]
        )
        self.assertEqual(result, ["ENABLED", "PAUSED"])

    def test_format_output_value_passthrough(self):
        """Tests that primitive values pass through unchanged."""

        self.assertEqual(utils.format_output_value("hello"), "hello")
        self.assertEqual(utils.format_output_value(42), 42)
        self.assertEqual(utils.format_output_value(3.14), 3.14)
        self.assertIsNone(utils.format_output_value(None))
