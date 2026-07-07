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

"""Test cases for the labels tool."""

import unittest
from unittest.mock import MagicMock, patch

from ads_mcp.tools import labels


class TestLabels(unittest.IsolatedAsyncioTestCase):
    """Test cases for the label management tools."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_label_service = MagicMock()
        self.mock_campaign_label_service = MagicMock()
        self.mock_customer_label_service = MagicMock()
        self.mock_ad_group_label_service = MagicMock()
        self.mock_ad_group_criterion_label_service = MagicMock()

        def get_service_mock(service_name, **kwargs):
            if service_name == "LabelService":
                return self.mock_label_service
            elif service_name == "CampaignLabelService":
                return self.mock_campaign_label_service
            elif service_name == "CustomerLabelService":
                return self.mock_customer_label_service
            elif service_name == "AdGroupLabelService":
                return self.mock_ad_group_label_service
            elif service_name == "AdGroupCriterionLabelService":
                return self.mock_ad_group_criterion_label_service
            return MagicMock()

        self.mock_client.get_service.side_effect = get_service_mock

        # Setup mock operations & types
        self.mock_label_op = MagicMock()
        self.mock_campaign_label_op = MagicMock()
        self.mock_customer_label_op = MagicMock()
        self.mock_ad_group_label_op = MagicMock()
        self.mock_ad_group_criterion_label_op = MagicMock()

        self.mock_label = MagicMock()
        self.mock_label_op.create = self.mock_label
        self.mock_label_op.update = self.mock_label

        self.mock_campaign_label = MagicMock()
        self.mock_campaign_label_op.create = self.mock_campaign_label

        self.mock_customer_label = MagicMock()
        self.mock_customer_label_op.create = self.mock_customer_label

        self.mock_ad_group_label = MagicMock()
        self.mock_ad_group_label_op.create = self.mock_ad_group_label

        self.mock_ad_group_criterion_label = MagicMock()
        self.mock_ad_group_criterion_label_op.create = self.mock_ad_group_criterion_label

        def get_type_mock(type_name):
            if type_name == "LabelOperation":
                return self.mock_label_op
            elif type_name == "Label":
                return MagicMock()
            elif type_name == "CampaignLabelOperation":
                return self.mock_campaign_label_op
            elif type_name == "CustomerLabelOperation":
                return self.mock_customer_label_op
            elif type_name == "AdGroupLabelOperation":
                return self.mock_ad_group_label_op
            elif type_name == "AdGroupCriterionLabelOperation":
                return self.mock_ad_group_criterion_label_op
            return MagicMock()

        self.mock_client.get_type.side_effect = get_type_mock

        # Default successful responses
        self.mock_mutate_response = MagicMock()
        mock_result = MagicMock()
        mock_result.resource_name = "customers/123/labels/456"
        self.mock_mutate_response.results = [mock_result]
        self.mock_label_service.mutate_labels.return_value = self.mock_mutate_response

        self.mock_campaign_response = MagicMock()
        mock_c_result = MagicMock()
        mock_c_result.resource_name = "customers/123/campaignLabels/456~789"
        self.mock_campaign_response.results = [mock_c_result]
        self.mock_campaign_label_service.mutate_campaign_labels.return_value = self.mock_campaign_response

        self.mock_customer_response = MagicMock()
        mock_cust_result = MagicMock()
        mock_cust_result.resource_name = "customers/123/customerLabels/123~789"
        self.mock_customer_response.results = [mock_cust_result]
        self.mock_customer_label_service.mutate_customer_labels.return_value = self.mock_customer_response

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_label(self, mock_get_client):
        """Tests Label creation with correct arguments."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_labels(
            customer_id="1234567890",
            operation="CREATE",
            name="Black Friday",
            background_color="#000000",
            description="Campaigns for Black Friday promotions",
        )

        self.assertEqual(self.mock_label.name, "Black Friday")
        self.assertEqual(self.mock_label.text_label.background_color, "#000000")
        self.assertEqual(self.mock_label.text_label.description, "Campaigns for Black Friday promotions")
        self.mock_label_service.mutate_labels.assert_called_once()
        self.assertIn("Successfully created label", result)
        self.assertIn("ID: 456", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_update_label(self, mock_get_client):
        """Tests Label updates and clean field mask generation."""
        mock_get_client.return_value = self.mock_client

        # Mock temp Label and copy_from / copy_to behaviour
        temp_label = MagicMock()
        temp_label._pb = MagicMock()
        
        def get_type_mock(type_name):
            if type_name == "LabelOperation":
                return self.mock_label_op
            elif type_name == "Label":
                return temp_label
            return MagicMock()
        self.mock_client.get_type.side_effect = get_type_mock

        result = await labels.manage_labels(
            customer_id="1234567890",
            operation="UPDATE",
            label_id="456",
            name="Updated Name",
        )

        self.assertEqual(self.mock_label.resource_name, "customers/1234567890/labels/456")
        self.assertEqual(self.mock_label.name, "Updated Name")
        self.mock_client.copy_from.assert_called_once()
        self.mock_label_service.mutate_labels.assert_called_once()
        self.assertIn("Successfully updated label", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_remove_label(self, mock_get_client):
        """Tests Label removal."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_labels(
            customer_id="1234567890",
            operation="REMOVE",
            label_id="456",
        )

        self.assertEqual(self.mock_label_op.remove, "customers/1234567890/labels/456")
        self.mock_label_service.mutate_labels.assert_called_once()
        self.assertIn("Successfully removed label", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_campaign_label_association(self, mock_get_client):
        """Tests CAMPAIGN label association creation."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
        )

        self.assertEqual(self.mock_campaign_label.campaign, "customers/1234567890/campaigns/456")
        self.assertEqual(self.mock_campaign_label.label, "customers/1234567890/labels/789")
        self.mock_campaign_label_service.mutate_campaign_labels.assert_called_once()
        self.assertIn("Successfully created CAMPAIGN label association", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_remove_campaign_label_association_by_name(self, mock_get_client):
        """Tests disassociation when passing direct association resource name."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            association_resource_name="customers/1234567890/campaignLabels/456~789",
        )

        self.assertEqual(self.mock_campaign_label_op.remove, "customers/1234567890/campaignLabels/456~789")
        self.mock_campaign_label_service.mutate_campaign_labels.assert_called_once()
        self.assertIn("Successfully removed CAMPAIGN label association", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_remove_campaign_label_association_by_ids(self, mock_get_client):
        """Tests disassociation when passing resource_id and label_id for auto-construction."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
        )

        self.assertEqual(self.mock_campaign_label_op.remove, "customers/1234567890/campaignLabels/456~789")
        self.mock_campaign_label_service.mutate_campaign_labels.assert_called_once()
        self.assertIn("Successfully removed CAMPAIGN label association", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_create_customer_label_association(self, mock_get_client):
        """Tests CUSTOMER label association creation."""
        mock_get_client.return_value = self.mock_client

        result = await labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="CUSTOMER",
            resource_id="1234567890",
            label_id="789",
        )

        self.assertEqual(self.mock_customer_label.customer, "customers/1234567890")
        self.assertEqual(self.mock_customer_label.label, "customers/1234567890/labels/789")
        self.mock_customer_label_service.mutate_customer_labels.assert_called_once()
        self.assertIn("Successfully created CUSTOMER label association", result)

    @patch("ads_mcp.utils.get_googleads_client")
    async def test_validation_errors(self, mock_get_client):
        """Tests invalid inputs throw errors without mutations."""
        mock_get_client.return_value = self.mock_client

        # Test invalid operation for manage_labels
        res = await labels.manage_labels(
            customer_id="123",
            operation="INVALID_OP",
        )
        self.assertIn("Error: Invalid operation", res)

        # Test missing name for Label CREATE
        res = await labels.manage_labels(
            customer_id="123",
            operation="CREATE",
        )
        self.assertIn("Error: 'name' is required", res)

        # Test missing label_id for Label UPDATE
        res = await labels.manage_labels(
            customer_id="123",
            operation="UPDATE",
            name="Some Name",
        )
        self.assertIn("Error: 'label_id' is required", res)

        # Test invalid association_type for manage_label_associations
        res = await labels.manage_label_associations(
            customer_id="123",
            operation="CREATE",
            association_type="INVALID_TYPE",
        )
        self.assertIn("Error: Invalid association_type", res)
