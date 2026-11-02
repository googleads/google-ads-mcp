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

import json
import unittest
from unittest.mock import MagicMock, create_autospec, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v25.services.services.ad_group_criterion_label_service import (
    AdGroupCriterionLabelServiceClient,
)
from google.ads.googleads.v25.services.services.ad_group_label_service import (
    AdGroupLabelServiceClient,
)
from google.ads.googleads.v25.services.services.campaign_label_service import (
    CampaignLabelServiceClient,
)
from google.ads.googleads.v25.services.services.customer_label_service import (
    CustomerLabelServiceClient,
)
from google.ads.googleads.v25.services.services.label_service import (
    LabelServiceClient,
)
from google.auth.credentials import AnonymousCredentials
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
from ads_mcp.tools import labels


class TestLabels(unittest.TestCase):
    """Test cases for the label management tools."""

    @classmethod
    def setUpClass(cls):
        cls.real_ga_client = GoogleAdsClient(
            credentials=AnonymousCredentials(),
            developer_token="fake-token",
            use_proto_plus=True,
        )

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_label_service = create_autospec(
            LabelServiceClient, instance=True
        )
        self.mock_campaign_label_service = create_autospec(
            CampaignLabelServiceClient, instance=True
        )
        self.mock_customer_label_service = create_autospec(
            CustomerLabelServiceClient, instance=True
        )
        self.mock_ad_group_label_service = create_autospec(
            AdGroupLabelServiceClient, instance=True
        )
        self.mock_ad_group_criterion_label_service = create_autospec(
            AdGroupCriterionLabelServiceClient, instance=True
        )

        def get_service_mock(service_name, **kwargs):
            if service_name == "LabelService":
                return self.mock_label_service
            if service_name == "CampaignLabelService":
                return self.mock_campaign_label_service
            if service_name == "CustomerLabelService":
                return self.mock_customer_label_service
            if service_name == "AdGroupLabelService":
                return self.mock_ad_group_label_service
            if service_name == "AdGroupCriterionLabelService":
                return self.mock_ad_group_criterion_label_service
            return MagicMock()

        self.mock_client.get_service.side_effect = get_service_mock
        self.mock_client.get_type.side_effect = self.real_ga_client.get_type

        def _make_resp(rn: str) -> MagicMock:
            resp = MagicMock()
            item = MagicMock()
            item.resource_name = rn
            resp.results = [item]
            return resp

        self.mock_label_service.mutate_labels.return_value = _make_resp(
            "customers/1234567890/labels/456"
        )
        self.mock_campaign_label_service.mutate_campaign_labels.return_value = (
            _make_resp("customers/1234567890/campaignLabels/456~789")
        )
        self.mock_customer_label_service.mutate_customer_labels.return_value = (
            _make_resp("customers/1234567890/customerLabels/1234567890~789")
        )
        self.mock_ad_group_label_service.mutate_ad_group_labels.return_value = (
            _make_resp("customers/1234567890/adGroupLabels/555~789")
        )
        self.mock_ad_group_criterion_label_service.mutate_ad_group_criterion_labels.return_value = _make_resp(
            "customers/1234567890/adGroupCriterionLabels/555~666~789"
        )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_create_label(self, mock_get_client):
        """Tests Label creation with propose/confirm, hyphenated customer_id, and interceptor."""
        mock_get_client.return_value = self.mock_client

        propose_res = labels.manage_labels(
            customer_id="123-456-7890",
            operation="CREATE",
            name="Black Friday",
            background_color="#000000",
            description="Campaigns for Black Friday promotions",
            login_customer_id="999-888-7777",
        )
        mock_get_client.assert_called_with(login_customer_id="999-888-7777")
        _, svc_kwargs = self.mock_client.get_service.call_args
        self.assertIsInstance(
            svc_kwargs["interceptors"][0], MCPHeaderInterceptor
        )

        proposal = json.loads(propose_res)
        self.assertEqual(proposal["status"], "PROPOSED")
        checksum = proposal["checksum"]

        propose_req = self.mock_label_service.mutate_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(propose_req.customer_id, "1234567890")
        self.assertTrue(propose_req.validate_only)

        result = labels.manage_labels(
            customer_id="123-456-7890",
            operation="CREATE",
            name="Black Friday",
            background_color="#000000",
            description="Campaigns for Black Friday promotions",
            login_customer_id="999-888-7777",
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_label_service.mutate_labels.call_args.kwargs[
            "request"
        ]
        created = commit_req.operations[0].create
        self.assertEqual(created.name, "Black Friday")
        self.assertEqual(created.text_label.background_color, "#000000")
        self.assertEqual(
            created.text_label.description,
            "Campaigns for Black Friday promotions",
        )
        self.assertFalse(commit_req.validate_only)
        self.assertIn("Successfully created label", result)
        self.assertIn("ID: 456", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_update_label_and_clear_description(self, mock_get_client):
        """Tests Label updates, FieldMask paths (including clearing to empty string), and primary_key_readable."""
        mock_get_client.return_value = self.mock_client

        propose_res = labels.manage_labels(
            customer_id="1234567890",
            operation="UPDATE",
            label_id="456",
            name="Updated Name",
            description="",
        )
        proposal = json.loads(propose_res)
        checksum = proposal["checksum"]
        self.assertEqual(
            proposal["change_items"][0]["primary_key_readable"],
            "customers/1234567890/labels/456",
        )

        result = labels.manage_labels(
            customer_id="1234567890",
            operation="UPDATE",
            label_id="456",
            name="Updated Name",
            description="",
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_label_service.mutate_labels.call_args.kwargs[
            "request"
        ]
        op = commit_req.operations[0]
        self.assertEqual(
            op.update.resource_name, "customers/1234567890/labels/456"
        )
        self.assertEqual(op.update.name, "Updated Name")
        self.assertEqual(op.update.text_label.description, "")
        self.assertEqual(
            list(op.update_mask.paths),
            ["name", "text_label.description"],
        )
        self.assertFalse(commit_req.validate_only)
        self.assertIn("Successfully updated label", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_remove_label(self, mock_get_client):
        """Tests Label removal."""
        mock_get_client.return_value = self.mock_client

        propose_res = labels.manage_labels(
            customer_id="1234567890",
            operation="REMOVE",
            label_id="456",
        )
        checksum = json.loads(propose_res)["checksum"]

        result = labels.manage_labels(
            customer_id="1234567890",
            operation="REMOVE",
            label_id="456",
            validate_only=False,
            checksum=checksum,
        )

        commit_req = self.mock_label_service.mutate_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            commit_req.operations[0].remove, "customers/1234567890/labels/456"
        )
        self.assertFalse(commit_req.validate_only)
        self.assertIn("Successfully removed label", result)

    @patch("ads_mcp.utils.get_googleads_client")
    def test_campaign_label_association_create_and_remove(
        self, mock_get_client
    ):
        """Tests CAMPAIGN label association creation and removal (by name and by IDs)."""
        mock_get_client.return_value = self.mock_client

        # CREATE
        propose_res = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
        )
        checksum = json.loads(propose_res)["checksum"]
        result = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
            validate_only=False,
            checksum=checksum,
        )
        req = self.mock_campaign_label_service.mutate_campaign_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            req.operations[0].create.campaign,
            "customers/1234567890/campaigns/456",
        )
        self.assertEqual(
            req.operations[0].create.label,
            "customers/1234567890/labels/789",
        )
        self.assertIn("Successfully created CAMPAIGN label association", result)

        # REMOVE by association_resource_name
        propose_rm_name = labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            association_resource_name="customers/1234567890/campaignLabels/456~789",
        )
        result_rm_name = labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            association_resource_name="customers/1234567890/campaignLabels/456~789",
            validate_only=False,
            checksum=json.loads(propose_rm_name)["checksum"],
        )
        req_rm = self.mock_campaign_label_service.mutate_campaign_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            req_rm.operations[0].remove,
            "customers/1234567890/campaignLabels/456~789",
        )
        self.assertIn(
            "Successfully removed CAMPAIGN label association", result_rm_name
        )

        # REMOVE by resource_id + label_id
        propose_rm_ids = labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
        )
        result_rm_ids = labels.manage_label_associations(
            customer_id="1234567890",
            operation="REMOVE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
            validate_only=False,
            checksum=json.loads(propose_rm_ids)["checksum"],
        )
        self.assertIn(
            "Successfully removed CAMPAIGN label association", result_rm_ids
        )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_customer_ad_group_and_criterion_associations(
        self, mock_get_client
    ):
        """Tests CUSTOMER (defaulting resource_id), AD_GROUP, and AD_GROUP_CRITERION associations."""
        mock_get_client.return_value = self.mock_client

        # CUSTOMER omitting resource_id defaults to cleaned customer_id
        propose_cust = labels.manage_label_associations(
            customer_id="123-456-7890",
            operation="CREATE",
            association_type="CUSTOMER",
            label_id="789",
        )
        res_cust = labels.manage_label_associations(
            customer_id="123-456-7890",
            operation="CREATE",
            association_type="CUSTOMER",
            label_id="789",
            validate_only=False,
            checksum=json.loads(propose_cust)["checksum"],
        )
        cust_req = self.mock_customer_label_service.mutate_customer_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            cust_req.operations[0].create.customer, "customers/1234567890"
        )
        self.assertIn(
            "Successfully created CUSTOMER label association", res_cust
        )

        # AD_GROUP
        propose_ag = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="AD_GROUP",
            resource_id="555",
            label_id="789",
        )
        res_ag = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="AD_GROUP",
            resource_id="555",
            label_id="789",
            validate_only=False,
            checksum=json.loads(propose_ag)["checksum"],
        )
        ag_req = self.mock_ad_group_label_service.mutate_ad_group_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            ag_req.operations[0].create.ad_group,
            "customers/1234567890/adGroups/555",
        )
        self.assertIn("Successfully created AD_GROUP label association", res_ag)

        # AD_GROUP_CRITERION with composite ad_group_id~criterion_id
        propose_agc = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="AD_GROUP_CRITERION",
            resource_id="555~666",
            label_id="789",
        )
        res_agc = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="AD_GROUP_CRITERION",
            resource_id="555~666",
            label_id="789",
            validate_only=False,
            checksum=json.loads(propose_agc)["checksum"],
        )
        agc_req = self.mock_ad_group_criterion_label_service.mutate_ad_group_criterion_labels.call_args.kwargs[
            "request"
        ]
        self.assertEqual(
            agc_req.operations[0].create.ad_group_criterion,
            "customers/1234567890/adGroupCriteria/555~666",
        )
        self.assertIn(
            "Successfully created AD_GROUP_CRITERION label association",
            res_agc,
        )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_validation_errors(self, mock_get_client):
        """Tests invalid inputs raise ToolError without mutations."""
        mock_get_client.return_value = self.mock_client

        with self.assertRaisesRegex(ToolError, "Invalid operation"):
            labels.manage_labels(
                customer_id="123",
                operation="INVALID_OP",  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(ToolError, "'name' is required"):
            labels.manage_labels(
                customer_id="123",
                operation="CREATE",
            )

        with self.assertRaisesRegex(ToolError, "'label_id' is required"):
            labels.manage_labels(
                customer_id="123",
                operation="UPDATE",
                name="Some Name",
            )

        with self.assertRaisesRegex(ToolError, "At least one field to update"):
            labels.manage_labels(
                customer_id="123",
                operation="UPDATE",
                label_id="456",
            )

        with self.assertRaisesRegex(ToolError, "Must be CREATE or REMOVE"):
            labels.manage_label_associations(
                customer_id="123",
                operation="UPDATE",  # type: ignore[arg-type]
                association_type="CAMPAIGN",
            )

        with self.assertRaisesRegex(ToolError, "Invalid association_type"):
            labels.manage_label_associations(
                customer_id="123",
                operation="CREATE",
                association_type="INVALID_TYPE",  # type: ignore[arg-type]
            )

        # Non-composite resource_id for AD_GROUP_CRITERION rejected
        with self.assertRaisesRegex(ToolError, "composite"):
            labels.manage_label_associations(
                customer_id="1234567890",
                operation="CREATE",
                association_type="AD_GROUP_CRITERION",
                resource_id="555",
                label_id="789",
            )

        # Bare ID passed as association_resource_name rejected
        with self.assertRaisesRegex(
            ToolError, "'association_resource_name' must start with"
        ):
            labels.manage_label_associations(
                customer_id="1234567890",
                operation="REMOVE",
                association_type="CAMPAIGN",
                association_resource_name="456~789",
            )

    @patch("ads_mcp.utils.get_googleads_client")
    def test_checksum_enforcement(self, mock_get_client):
        """Tests that missing or mismatched checksums raise ToolError for label tools."""
        mock_get_client.return_value = self.mock_client

        with self.assertRaisesRegex(
            ToolError,
            "checksum from a previous validate_only=True call is required",
        ):
            labels.manage_labels(
                customer_id="1234567890",
                operation="CREATE",
                name="Promo",
                validate_only=False,
            )
        self.mock_label_service.mutate_labels.assert_not_called()

        propose_res = labels.manage_label_associations(
            customer_id="1234567890",
            operation="CREATE",
            association_type="CAMPAIGN",
            resource_id="456",
            label_id="789",
        )
        checksum = json.loads(propose_res)["checksum"]
        self.assertEqual(
            self.mock_campaign_label_service.mutate_campaign_labels.call_count,
            1,
        )

        with self.assertRaisesRegex(
            ToolError, "Invalid or mismatched checksum"
        ):
            labels.manage_label_associations(
                customer_id="1234567890",
                operation="CREATE",
                association_type="CAMPAIGN",
                resource_id="999",
                label_id="789",
                validate_only=False,
                checksum=checksum,
            )
        self.assertEqual(
            self.mock_campaign_label_service.mutate_campaign_labels.call_count,
            1,
        )


if __name__ == "__main__":
    unittest.main()
