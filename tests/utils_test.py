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
from google.ads.googleads.v23.enums.types.campaign_status import (
    CampaignStatusEnum,
)

from ads_mcp.utils import _to_proto_attr, format_output_value


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def test_format_output_value(self):
        """Tests that output values are formatted correctly."""

        self.assertEqual(
            format_output_value(CampaignStatusEnum.CampaignStatus.ENABLED),
            "ENABLED",
        )

    def test_to_proto_attr_reserved_type(self):
        """Tests that 'type' is converted to 'type_' in attribute paths."""

        self.assertEqual(_to_proto_attr("ad.type"), "ad.type_")
        self.assertEqual(
            _to_proto_attr("ad_group_ad.ad.type"),
            "ad_group_ad.ad.type_",
        )
        self.assertEqual(
            _to_proto_attr("conversion_action.type"),
            "conversion_action.type_",
        )

    def test_to_proto_attr_no_change(self):
        """Tests that non-reserved attributes are unchanged."""

        self.assertEqual(_to_proto_attr("campaign.name"), "campaign.name")
        self.assertEqual(_to_proto_attr("metrics.clicks"), "metrics.clicks")
