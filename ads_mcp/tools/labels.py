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

"""Tools for managing Labels and Label Associations in Google Ads."""

from enum import Enum
from typing import Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils
from google.api_core import protobuf_helpers


class AssociationType(str, Enum):
    """Enum representing the type of resource being associated with a label."""

    CAMPAIGN = "CAMPAIGN"
    CUSTOMER = "CUSTOMER"
    AD_GROUP = "AD_GROUP"
    AD_GROUP_CRITERION = "AD_GROUP_CRITERION"



def _extract_id(resource_name_or_id: str) -> str:
    """Extracts the last component (the ID) from a resource name or returns the ID as-is."""
    if "/" in resource_name_or_id:
        return resource_name_or_id.split("/")[-1]
    return resource_name_or_id


def _get_label_resource_name(customer_id: str, label: str) -> str:
    """Ensures a label has a full resource name."""
    if label.startswith("customers/"):
        return label
    return f"customers/{customer_id}/labels/{label}"


ASSOCIATION_CONFIGS = {
    "CAMPAIGN": {
        "service": "CampaignLabelService",
        "operation": "CampaignLabelOperation",
        "mutate_method": "mutate_campaign_labels",
        "resource_field": "campaign",
        "label_field": "label",
        "resource_prefix": "campaignLabels",
    },
    "CUSTOMER": {
        "service": "CustomerLabelService",
        "operation": "CustomerLabelOperation",
        "mutate_method": "mutate_customer_labels",
        "resource_field": "customer",
        "label_field": "label",
        "resource_prefix": "customerLabels",
    },
    "AD_GROUP": {
        "service": "AdGroupLabelService",
        "operation": "AdGroupLabelOperation",
        "mutate_method": "mutate_ad_group_labels",
        "resource_field": "ad_group",
        "label_field": "label",
        "resource_prefix": "adGroupLabels",
    },
    "AD_GROUP_CRITERION": {
        "service": "AdGroupCriterionLabelService",
        "operation": "AdGroupCriterionLabelOperation",
        "mutate_method": "mutate_ad_group_criterion_labels",
        "resource_field": "ad_group_criterion",
        "label_field": "label",
        "resource_prefix": "adGroupCriterionLabels",
    },
}


def _construct_association_resource_name(
    customer_id: str,
    association_type: AssociationType,
    resource_name: str,
    label_resource_name: str,
) -> str:
    config = ASSOCIATION_CONFIGS.get(association_type.upper())
    if not config:
        raise ValueError(f"Invalid association type: {association_type}")

    resource_id = _extract_id(resource_name)
    label_id = _extract_id(label_resource_name)
    prefix = config["resource_prefix"]

    return f"customers/{customer_id}/{prefix}/{resource_id}~{label_id}"


@mcp.tool
async def manage_labels(
    customer_id: str,
    operation: utils.MutateOperation,
    name: Optional[str] = None,
    background_color: Optional[str] = None,
    description: Optional[str] = None,
    resource_name: Optional[str] = None,
) -> str:
    """Manages Label resources. Supports CREATE, UPDATE, and REMOVE operations.

    Args:
        customer_id: Google Ads Customer ID (without hyphens).
        operation: The operation to perform. Must be 'CREATE', 'UPDATE', or 'REMOVE'.
        name: The name of the label. Required for CREATE, optional for UPDATE.
        background_color: Background color in HTML hex format (e.g., '#FF0000'). Optional.
        description: Description of the label. Optional.
        resource_name: The resource name of the label (e.g., 'customers/123/labels/456').
                       Required for UPDATE and REMOVE.

    Returns:
        A string indicating the success and the mutated label's resource name, or an error message.
    """
    ga_client = utils.get_googleads_client()
    label_service = ga_client.get_service("LabelService")
    op_upper = operation.upper()

    if op_upper not in ["CREATE", "UPDATE", "REMOVE"]:
        return f"Error: Invalid operation '{operation}'. Must be one of: CREATE, UPDATE, REMOVE."

    label_op = ga_client.get_type("LabelOperation")

    if op_upper == "CREATE":
        if not name:
            return "Error: 'name' is required for CREATE operation."
        label = label_op.create
        label.name = name
        if background_color:
            label.text_label.background_color = background_color
        if description:
            label.text_label.description = description

    elif op_upper == "UPDATE":
        if not resource_name:
            return "Error: 'resource_name' is required for UPDATE operation."

        # Use temp object to cleanly build the update mask
        temp_label = ga_client.get_type("Label")
        has_updates = False
        if name is not None:
            temp_label.name = name
            has_updates = True
        if background_color is not None:
            temp_label.text_label.background_color = background_color
            has_updates = True
        if description is not None:
            temp_label.text_label.description = description
            has_updates = True

        if not has_updates:
            return "Error: At least one field to update ('name', 'background_color', or 'description') must be provided."

        mask = protobuf_helpers.field_mask(None, temp_label._pb)

        label = label_op.update
        label.resource_name = resource_name
        if name is not None:
            label.name = name
        if background_color is not None:
            label.text_label.background_color = background_color
        if description is not None:
            label.text_label.description = description

        ga_client.copy_from(label_op.update_mask, mask)

    elif op_upper == "REMOVE":
        if not resource_name:
            return "Error: 'resource_name' is required for REMOVE operation."
        label_op.remove = resource_name

    try:
        response = label_service.mutate_labels(
            customer_id=customer_id, operations=[label_op]
        )
        res_name = response.results[0].resource_name
        action_past = "created" if op_upper == "CREATE" else "updated" if op_upper == "UPDATE" else "removed"
        return f"Successfully {action_past} label. Resource Name: {res_name}"
    except Exception as e:
        utils.logger.error(f"Failed to {op_upper.lower()} label: {e}")
        return f"Failed to {op_upper.lower()} label: {e}"


@mcp.tool
async def manage_label_associations(
    customer_id: str,
    operation: utils.MutateOperation,
    association_type: AssociationType,
    resource_name: Optional[str] = None,
    label_resource_name: Optional[str] = None,
    association_resource_name: Optional[str] = None,
) -> str:
    """Manages associations between labels and Campaign, Customer, Ad Group, or Ad Group Criterion.

    Supports CREATE and REMOVE operations.

    Args:
        customer_id: Google Ads Customer ID (without hyphens).
        operation: The operation to perform. Must be 'CREATE' or 'REMOVE'.
        association_type: The type of resource being associated.
                          Must be 'CAMPAIGN', 'CUSTOMER', 'AD_GROUP', or 'AD_GROUP_CRITERION'.
        resource_name: The full resource name of the entity to associate (e.g., 'customers/123/campaigns/456').
                       Required for CREATE.
        label_resource_name: The full resource name of the Label (e.g., 'customers/123/labels/789').
                             Required for CREATE.
        association_resource_name: The full resource name of the association itself
                                   (e.g., 'customers/123/campaignLabels/456~789').
                                   Required for REMOVE if resource_name and label_resource_name are not provided.

    Returns:
        A string indicating success and the resource name of the association, or an error message.
    """
    op_upper = operation.upper()
    type_upper = association_type.upper()

    if op_upper not in ["CREATE", "REMOVE"]:
        return f"Error: Invalid operation '{operation}'. Must be CREATE or REMOVE."

    config = ASSOCIATION_CONFIGS.get(type_upper)
    if not config:
        valid_types = ", ".join(ASSOCIATION_CONFIGS.keys())
        return f"Error: Invalid association_type '{association_type}'. Must be one of: {valid_types}."

    ga_client = utils.get_googleads_client()
    service = ga_client.get_service(config["service"])
    op = ga_client.get_type(config["operation"])

    if op_upper == "CREATE":
        if not resource_name:
            return f"Error: 'resource_name' is required to CREATE a {type_upper} label association."
        if not label_resource_name:
            return "Error: 'label_resource_name' is required to CREATE a label association."

        association = op.create
        setattr(association, config["resource_field"], resource_name)
        setattr(association, config["label_field"], label_resource_name)

    elif op_upper == "REMOVE":
        target_rn = association_resource_name
        if not target_rn:
            if not resource_name or not label_resource_name:
                return (
                    "Error: For REMOVE operation, you must provide either "
                    "'association_resource_name' OR both 'resource_name' and 'label_resource_name'."
                )
            try:
                target_rn = _construct_association_resource_name(
                    customer_id, type_upper, resource_name, label_resource_name
                )
            except Exception as e:
                return f"Error constructing association resource name: {e}"

        op.remove = target_rn

    mutate_method = getattr(service, config["mutate_method"])

    try:
        response = mutate_method(customer_id=customer_id, operations=[op])
        res_name = response.results[0].resource_name
        action_past = "created" if op_upper == "CREATE" else "removed"
        return f"Successfully {action_past} {type_upper} label association. Resource Name: {res_name}"
    except Exception as e:
        utils.logger.error(f"Failed to {op_upper.lower()} {type_upper} label association: {e}")
        return f"Failed to {op_upper.lower()} {type_upper} label association: {e}"
