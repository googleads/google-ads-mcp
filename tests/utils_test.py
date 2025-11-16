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

from ads_mcp import utils
from google.ads.googleads.v21.enums.types.campaign_status import (
    CampaignStatusEnum,
)


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def test_format_output_value(self) -> None:
        """Tests that output values are formatted correctly."""

        client = utils._get_googleads_client(  # noqa: F841
            credentials={},
        )
        self.assertEqual(
            utils.format_output_value(
                CampaignStatusEnum.CampaignStatus.ENABLED
            ),
            "ENABLED",
        )
