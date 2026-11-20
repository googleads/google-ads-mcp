"""Tests for campaign mutation safeguards."""

import unittest
from fastmcp.exceptions import ToolError

from ads_mcp import propose_and_confirm as pac
from ads_mcp.tools.campaigns import manage_campaign


class CampaignToolsTest(unittest.TestCase):
    def test_create_requires_campaign_inputs(self):
        with self.assertRaises(ToolError):
            manage_campaign(customer_id="123", operation="CREATE", name="Test")

    def test_checksum_binds_campaign_parameters(self):
        original = {
            "tool": "manage_campaign",
            "operation": "UPDATE",
            "campaign_id": "456",
            "name": "Old name",
        }
        checksum = pac.compute_checksum("123", original)
        changed = {**original, "name": "New name"}
        self.assertIsNotNone(pac.verify_checksum("123", changed, checksum))
