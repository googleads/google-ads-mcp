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
from fastmcp import FastMCP
from typing import Optional
import ads_mcp.utils as utils
from google.api_core import protobuf_helpers

labels_mcp = FastMCP("labels")


class AssociationType(str, Enum):
    """Enum representing the type of resource being associated with a label."""

    CAMPAIGN = "CAMPAIGN"
    CUSTOMER = "CUSTOMER"
    AD_GROUP = "AD_GROUP"
    AD_GROUP_CRITERION = "AD_GROUP_CRITERION"


def _get_label_resource_name(customer_id: str, label: str) -> str:
    """Ensures a label has a full resource name."""
    if label.startswith("customers/"):
        return label
    return f"customers/{customer_id}/labels/{label}"


ASSOCIATION_CONFIGS = {
    "CAMPAIGN": {
        "service": "CampaignLabelService",
        "request": "MutateCampaignLabelsRequest",
        "operation": "CampaignLabelOperation",
        "mutate_method": "mutate_campaign_labels",
        "resource_field": "campaign",
        "label_field": "label",
        "resource_prefix": "campaignLabels",
        "entity_prefix": "campaigns",
    },
    "CUSTOMER": {
        "service": "CustomerLabelService",
        "request": "MutateCustomerLabelsRequest",
        "operation": "CustomerLabelOperation",
        "mutate_method": "mutate_customer_labels",
        "resource_field": "customer",
        "label_field": "label",
        "resource_prefix": "customerLabels",
        "entity_prefix": "customers",
    },
    "AD_GROUP": {
        "service": "AdGroupLabelService",
        "request": "MutateAdGroupLabelsRequest",
        "operation": "AdGroupLabelOperation",
        "mutate_method": "mutate_ad_group_labels",
        "resource_field": "ad_group",
        "label_field": "label",
        "resource_prefix": "adGroupLabels",
        "entity_prefix": "adGroups",
    },
    "AD_GROUP_CRITERION": {
        "service": "AdGroupCriterionLabelService",
        "request": "MutateAdGroupCriterionLabelsRequest",
        "operation": "AdGroupCriterionLabelOperation",
        "mutate_method": "mutate_ad_group_criterion_labels",
        "resource_field": "ad_group_criterion",
        "label_field": "label",
        "resource_prefix": "adGroupCriterionLabels",
        "entity_prefix": "adGroupCriteria",
    },
}


def _construct_association_resource_name(
    customer_id: str,
    association_type: AssociationType,
    resource_id: str,
    label_id: str,
) -> str:
    config = ASSOCIATION_CONFIGS.get(association_type.upper())
    if not config:
        raise ValueError(f"Invalid association type: {association_type}")

    prefix = config["resource_prefix"]

    return f"customers/{customer_id}/{prefix}/{resource_id}~{label_id}"


@labels_mcp.tool
async def manage_labels(
    customer_id: str,
    operation: utils.MutateOperation,
    name: Optional[str] = None,
    background_color: Optional[str] = None,
    description: Optional[str] = None,
    label_id: Optional[str] = None,
    validate_only: bool = True,
    checksum: Optional[str] = None,
) -> str:
    """Manages Label resources. Supports CREATE, UPDATE, and REMOVE operations.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `manage_labels` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without committing changes.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `manage_labels` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (without hyphens).
        operation: The operation to perform. Must be 'CREATE', 'UPDATE', or 'REMOVE'.
        name: The name of the label. Required for CREATE, optional for UPDATE.
        background_color: Background color in HTML hex format (e.g., '#FF0000'). Optional.
        description: Description of the label. Optional.
        label_id: The ID of the label (e.g., '456').
                  Required for UPDATE and REMOVE.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without mutating the label. If False, requires `checksum` from a prior `validate_only=True` call to commit the mutation.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.

    Returns:
        When `validate_only=True`, a JSON proposal containing `change_items` and `checksum`. When `validate_only=False`, a string indicating the success and the mutated label's ID, or an error message.
    """
    ga_client = utils.get_googleads_client()
    label_service = ga_client.get_service("LabelService")
    op_upper = operation.upper()

    if op_upper not in ["CREATE", "UPDATE", "REMOVE"]:
        return f"Error: Invalid operation '{operation}'. Must be one of: CREATE, UPDATE, REMOVE."

    label_op = ga_client.get_type("LabelOperation")
    target_resource_name: Optional[str] = None

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
        if not label_id:
            return "Error: 'label_id' is required for UPDATE operation."

        target_resource_name = f"customers/{customer_id}/labels/{label_id}"

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
        label.resource_name = target_resource_name
        if name is not None:
            label.name = name
        if background_color is not None:
            label.text_label.background_color = background_color
        if description is not None:
            label.text_label.description = description

        ga_client.copy_from(label_op.update_mask, mask)

    elif op_upper == "REMOVE":
        if not label_id:
            return "Error: 'label_id' is required for REMOVE operation."
        target_resource_name = f"customers/{customer_id}/labels/{label_id}"
        label_op.remove = target_resource_name

    operation_payload = {
        "tool": "manage_labels",
        "operation": op_upper,
        "name": name,
        "background_color": background_color,
        "description": description,
        "label_id": label_id,
    }

    change_items = utils.build_change_items(
        operation=op_upper,
        entity_readable="Label",
        primary_key_readable=name or target_resource_name or "",
        fields={
            "Label ID": label_id,
            "Resource Name": target_resource_name,
            "Name": name,
            "Background Color": background_color,
            "Description": description,
        },
    )

    request = ga_client.get_type("MutateLabelsRequest")
    request.customer_id = customer_id
    request.operations.append(label_op)
    request.validate_only = validate_only

    def _validate() -> None:
        request.validate_only = True
        label_service.mutate_labels(request=request)

    def _commit() -> str:
        request.validate_only = False
        response = label_service.mutate_labels(request=request)
        res_name = response.results[0].resource_name
        res_id = utils.extract_id(res_name)
        action_past = (
            "created"
            if op_upper == "CREATE"
            else "updated" if op_upper == "UPDATE" else "removed"
        )
        return f"Successfully {action_past} label. ID: {res_id}"

    return utils.propose_and_confirm(
        customer_id=customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=_validate,
        commit_fn=_commit,
        error_prefix=f"Failed to {op_upper.lower()} label",
    )


@labels_mcp.tool
async def manage_label_associations(
    customer_id: str,
    operation: utils.MutateOperation,
    association_type: AssociationType,
    resource_id: Optional[str] = None,
    label_id: Optional[str] = None,
    association_resource_name: Optional[str] = None,
    validate_only: bool = True,
    checksum: Optional[str] = None,
) -> str:
    """Manages associations between labels and Campaign, Customer, Ad Group, or Ad Group Criterion.

    Supports CREATE and REMOVE operations.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `manage_label_associations` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without committing changes.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `manage_label_associations` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (without hyphens).
        operation: The operation to perform. Must be 'CREATE' or 'REMOVE'.
        association_type: The type of resource being associated.
                          Must be 'CAMPAIGN', 'CUSTOMER', 'AD_GROUP', or 'AD_GROUP_CRITERION'.
        resource_id: The flat ID of the entity to associate (e.g., '456' for campaign).
                     Required for CREATE.
        label_id: The flat ID of the Label (e.g., '789').
                  Required for CREATE.
        association_resource_name: The full resource name of the association itself
                                   (e.g., 'customers/123/campaignLabels/456~789').
                                   Required for REMOVE if resource_id and label_id are not provided.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without mutating the association. If False, requires `checksum` from a prior `validate_only=True` call to commit the mutation.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.

    Returns:
        When `validate_only=True`, a JSON proposal containing `change_items` and `checksum`. When `validate_only=False`, a string indicating success and the ID of the association, or an error message.
    """
    op_upper = operation.upper()
    type_upper = association_type.upper()

    if op_upper not in ["CREATE", "REMOVE"]:
        return (
            f"Error: Invalid operation '{operation}'. Must be CREATE or REMOVE."
        )

    config = ASSOCIATION_CONFIGS.get(type_upper)
    if not config:
        valid_types = ", ".join(ASSOCIATION_CONFIGS.keys())
        return f"Error: Invalid association_type '{association_type}'. Must be one of: {valid_types}."

    ga_client = utils.get_googleads_client()
    service = ga_client.get_service(config["service"])
    op = ga_client.get_type(config["operation"])

    resource_name: Optional[str] = None
    label_resource_name: Optional[str] = None
    target_rn: Optional[str] = None

    if op_upper == "CREATE":
        if not resource_id:
            return f"Error: 'resource_id' is required to CREATE a {type_upper} label association."
        if not label_id:
            return (
                "Error: 'label_id' is required to CREATE a label association."
            )

        entity_prefix = config["entity_prefix"]

        if type_upper == "CUSTOMER":
            # Customer resource name is just customers/{resource_id}
            resource_name = f"customers/{resource_id}"
        else:
            resource_name = (
                f"customers/{customer_id}/{entity_prefix}/{resource_id}"
            )

        label_resource_name = f"customers/{customer_id}/labels/{label_id}"

        association = op.create
        setattr(association, config["resource_field"], resource_name)
        setattr(association, config["label_field"], label_resource_name)

    elif op_upper == "REMOVE":
        target_rn = association_resource_name
        if not target_rn:
            if not resource_id or not label_id:
                return (
                    "Error: For REMOVE operation, you must provide either "
                    "'association_resource_name' OR both 'resource_id' and 'label_id'."
                )
            try:
                target_rn = _construct_association_resource_name(
                    customer_id, type_upper, resource_id, label_id
                )
            except Exception as e:
                return f"Error constructing association resource name: {e}"

        op.remove = target_rn

    mutate_method = getattr(service, config["mutate_method"])

    operation_payload = {
        "tool": "manage_label_associations",
        "operation": op_upper,
        "association_type": type_upper,
        "resource_id": resource_id,
        "label_id": label_id,
        "association_resource_name": association_resource_name,
        "target_resource_name": target_rn,
    }

    change_items = utils.build_change_items(
        operation=op_upper,
        entity_readable=f"{type_upper} Label Association",
        primary_key_readable=(
            target_rn if op_upper == "REMOVE" else f"{resource_name}~{label_id}"
        ),
        fields={
            "Association Type": type_upper,
            "Resource": resource_name,
            "Label": label_resource_name,
            "Association Resource Name": target_rn,
        },
    )

    request = ga_client.get_type(config["request"])
    request.customer_id = customer_id
    request.operations.append(op)
    request.validate_only = validate_only

    def _validate() -> None:
        request.validate_only = True
        mutate_method(request=request)

    def _commit() -> str:
        request.validate_only = False
        response = mutate_method(request=request)
        res_name = response.results[0].resource_name
        res_id = utils.extract_id(res_name)
        action_past = "created" if op_upper == "CREATE" else "removed"
        return f"Successfully {action_past} {type_upper} label association. ID: {res_id}"

    return utils.propose_and_confirm(
        customer_id=customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=_validate,
        commit_fn=_commit,
        error_prefix=f"Failed to {op_upper.lower()} {type_upper} label association",
    )
