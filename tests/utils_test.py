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
import json
from google.ads.googleads.v23.enums.types.campaign_status import (
    CampaignStatusEnum,
)

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

    def test_format_output_value_repeated_scalar(self):
        """Tests that repeated scalar fields (e.g. final_urls) are serialized to lists."""
        client = utils.get_googleads_client()
        ad_type = client.get_type("Ad")
        ad_type.final_urls.append("https://www.example.com")
        ad_type.final_urls.append("https://www.example.com/page2")

        result = utils.format_output_value(ad_type.final_urls)
        self.assertEqual(result, ["https://www.example.com", "https://www.example.com/page2"])
        json.dumps(result)  # must be JSON-serializable

    def test_format_output_value_empty_repeated(self):
        """Tests that empty repeated fields serialize to empty lists."""
        client = utils.get_googleads_client()
        ad_type = client.get_type("Ad")

        result = utils.format_output_value(ad_type.final_urls)
        self.assertEqual(result, [])

    def test_format_output_value_primitives(self):
        """Tests that primitive types pass through unchanged."""
        self.assertEqual(utils.format_output_value("hello"), "hello")
        self.assertEqual(utils.format_output_value(42), 42)
        self.assertEqual(utils.format_output_value(3.14), 3.14)
        self.assertEqual(utils.format_output_value(True), True)

    def test_format_output_value_proto_message(self):
        """Tests that protobuf Message types are serialized to dicts."""
        client = utils.get_googleads_client()
        money_type = client.get_type("Money")
        money_type.amount_micros = 5000000
        money_type.currency_code = "USD"

        result = utils.format_output_value(money_type)
        self.assertIsInstance(result, dict)
        json.dumps(result)  # must be JSON-serializable
        self.assertEqual(result["currencyCode"], "USD")
        self.assertEqual(result["amountMicros"], "5000000")

    def test_format_output_value_repeated_composite(self):
        """Tests that repeated composite fields (e.g. headlines) are serialized to list of dicts."""
        client = utils.get_googleads_client()
        ad_type = client.get_type("Ad")
        headline = client.get_type("AdTextAsset")
        headline.text = "Test Headline"
        ad_type.responsive_search_ad.headlines.append(headline)

        result = utils.format_output_value(ad_type.responsive_search_ad.headlines)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]["text"], "Test Headline")
        json.dumps(result)  # must be JSON-serializable
