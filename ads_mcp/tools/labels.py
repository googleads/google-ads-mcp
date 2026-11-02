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
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp import propose_and_confirm as pac
import ads_mcp.utils as utils

labels_mcp = FastMCP("labels")


class AssociationOperation(str, Enum):
    """Supported mutate operations for label associations."""

    CREATE = "CREATE"
    REMOVE = "REMOVE"


class AssociationType(str, Enum):
    """Enum representing the type of resource being associated with a label."""

    CAMPAIGN = "CAMPAIGN"
    CUSTOMER = "CUSTOMER"
    AD_GROUP = "AD_GROUP"
    AD_GROUP_CRITERION = "AD_GROUP_CRITERION"


ASSOCIATION_CONFIGS: dict[str, dict[str, str]] = {
    AssociationType.CAMPAIGN.value: {
        "service": "CampaignLabelService",
        "request": "MutateCampaignLabelsRequest",
        "operation": "CampaignLabelOperation",
        "mutate_method": "mutate_campaign_labels",
        "resource_field": "campaign",
        "label_field": "label",
        "resource_prefix": "campaignLabels",
        "entity_prefix": "campaigns",
    },
    AssociationType.CUSTOMER.value: {
        "service": "CustomerLabelService",
        "request": "MutateCustomerLabelsRequest",
        "operation": "CustomerLabelOperation",
        "mutate_method": "mutate_customer_labels",
        "resource_field": "customer",
        "label_field": "label",
        "resource_prefix": "customerLabels",
        "entity_prefix": "customers",
    },
    AssociationType.AD_GROUP.value: {
        "service": "AdGroupLabelService",
        "request": "MutateAdGroupLabelsRequest",
        "operation": "AdGroupLabelOperation",
        "mutate_method": "mutate_ad_group_labels",
        "resource_field": "ad_group",
        "label_field": "label",
        "resource_prefix": "adGroupLabels",
        "entity_prefix": "adGroups",
    },
    AssociationType.AD_GROUP_CRITERION.value: {
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


def _validate_resource_id_for_type(type_upper: str, resource_id: str) -> str:
    """Validates and normalizes resource_id for the given association type."""
    cleaned = resource_id.strip()
    if type_upper == AssociationType.CUSTOMER.value:
        cleaned = utils.clean_customer_id(cleaned)
        if not cleaned:
            raise ToolError(
                "Error: 'resource_id' for CUSTOMER association must contain digits."
            )
        return cleaned

    if type_upper == AssociationType.AD_GROUP_CRITERION.value:
        parts = cleaned.split("~")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ToolError(
                "Error: For 'AD_GROUP_CRITERION', 'resource_id' must be in composite "
                "'{ad_group_id}~{criterion_id}' format (e.g., '456~789')."
            )
    return cleaned


def _construct_association_resource_name(
    customer_id: str,
    association_type: AssociationType | str,
    resource_id: str,
    label_id: str,
) -> str:
    config = ASSOCIATION_CONFIGS.get(str(association_type).upper())
    if not config:
        raise ValueError(f"Invalid association type: {association_type}")

    prefix = config["resource_prefix"]
    return f"customers/{customer_id}/{prefix}/{resource_id}~{label_id}"


@labels_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def manage_labels(
    customer_id: str | int,
    operation: utils.MutateOperation,
    name: str | None = None,
    background_color: str | None = None,
    description: str | None = None,
    label_id: str | None = None,
    login_customer_id: str | int | None = None,
    validate_only: bool = True,
    checksum: str | None = None,
) -> str:
    """Manages Label resources. Supports CREATE, UPDATE, and REMOVE operations.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `manage_labels` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without committing changes.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `manage_labels` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (digits or hyphenated, e.g. '1234567890').
        operation: The operation to perform. Must be 'CREATE', 'UPDATE', or 'REMOVE'.
        name: The name of the label. Required for CREATE, optional for UPDATE.
        background_color: Background color in HTML hex format (e.g., '#FF0000'). Optional.
        description: Description of the label. Optional.
        label_id: The ID of the label (e.g., '456'). Required for UPDATE and REMOVE.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without mutating the label. If False, requires `checksum` from a prior `validate_only=True` call to commit the mutation.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.
    """
    cleaned_customer_id = utils.clean_customer_id(customer_id)
    if not cleaned_customer_id:
        raise ToolError("Error: 'customer_id' must contain digits.")

    op_upper = (
        operation.value
        if isinstance(operation, utils.MutateOperation)
        else str(operation).upper()
    )
    if op_upper not in utils.MutateOperation.__members__:
        raise ToolError(
            f"Error: Invalid operation '{operation}'. Must be one of: CREATE, UPDATE, REMOVE."
        )

    ga_client = utils.get_googleads_client(login_customer_id=login_customer_id)
    label_service = utils.get_googleads_service_from_client(
        ga_client, "LabelService"
    )

    label_op = ga_client.get_type("LabelOperation")
    target_resource_name: str | None = None

    if op_upper == "CREATE":
        if not name:
            raise ToolError("Error: 'name' is required for CREATE operation.")
        label = label_op.create
        label.name = name
        if background_color:
            label.text_label.background_color = background_color
        if description:
            label.text_label.description = description

    elif op_upper == "UPDATE":
        if not label_id:
            raise ToolError(
                "Error: 'label_id' is required for UPDATE operation."
            )

        target_resource_name = (
            f"customers/{cleaned_customer_id}/labels/{label_id}"
        )
        label = label_op.update
        label.resource_name = target_resource_name

        update_paths: list[str] = []
        if name is not None:
            label.name = name
            update_paths.append("name")
        if background_color is not None:
            label.text_label.background_color = background_color
            update_paths.append("text_label.background_color")
        if description is not None:
            label.text_label.description = description
            update_paths.append("text_label.description")

        if not update_paths:
            raise ToolError(
                "Error: At least one field to update ('name', 'background_color', "
                "or 'description') must be provided."
            )

        label_op.update_mask.paths.extend(update_paths)

    elif op_upper == "REMOVE":
        if not label_id:
            raise ToolError(
                "Error: 'label_id' is required for REMOVE operation."
            )
        target_resource_name = (
            f"customers/{cleaned_customer_id}/labels/{label_id}"
        )
        label_op.remove = target_resource_name

    operation_payload = {
        "tool": "manage_labels",
        "operation": op_upper,
        "name": name,
        "background_color": background_color,
        "description": description,
        "label_id": label_id,
    }

    change_items = pac.build_change_items(
        operation=op_upper,
        entity_readable="Label",
        primary_key_readable=target_resource_name or name or "",
        fields={
            "Label ID": label_id,
            "Resource Name": target_resource_name,
            "Name": name,
            "Background Color": background_color,
            "Description": description,
        },
    )

    request = ga_client.get_type("MutateLabelsRequest")
    request.customer_id = cleaned_customer_id
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

    return pac.propose_and_confirm(
        customer_id=cleaned_customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=_validate,
        commit_fn=_commit,
        error_prefix=f"Failed to {op_upper.lower()} label",
    )


@labels_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def manage_label_associations(
    customer_id: str | int,
    operation: AssociationOperation,
    association_type: AssociationType,
    resource_id: str | None = None,
    label_id: str | None = None,
    association_resource_name: str | None = None,
    login_customer_id: str | int | None = None,
    validate_only: bool = True,
    checksum: str | None = None,
) -> str:
    """Manages associations between labels and Campaign, Customer, Ad Group, or Ad Group Criterion.

    Supports CREATE and REMOVE operations.

    Propose & Confirm Workflow (`validate_only` and `checksum`):
    1. Call `manage_label_associations` with `validate_only=True` (the default). After validation passes, the tool returns structured `change_items` and a `checksum` without committing changes.
    2. Present the `change_items` to the user and wait for explicit user approval.
    3. Only after user confirmation, call `manage_label_associations` with `validate_only=False` along with the exact same parameters and the `checksum` returned by the previous `validate_only=True` call.

    Args:
        customer_id: Google Ads Customer ID (digits or hyphenated, e.g. '1234567890').
        operation: The operation to perform. Must be 'CREATE' or 'REMOVE'.
        association_type: The type of resource being associated.
            Must be 'CAMPAIGN', 'CUSTOMER', 'AD_GROUP', or 'AD_GROUP_CRITERION'.
        resource_id: The ID of the entity to associate (e.g., '456' for CAMPAIGN or AD_GROUP,
            or composite '{ad_group_id}~{criterion_id}' such as '456~789' for AD_GROUP_CRITERION).
            Optional for CUSTOMER (defaults to `customer_id`); required for CREATE on other types.
        label_id: The ID of the Label (e.g., '789'). Required for CREATE.
        association_resource_name: The full resource name of the association itself
            (e.g., 'customers/123/campaignLabels/456~789'). Optional alternative for REMOVE
            when `resource_id` and `label_id` are not provided.
        login_customer_id: Optional manager customer ID to use as the login-customer-id header.
        validate_only: If True (default), validates the request and returns proposed `change_items` and a `checksum` without mutating the association. If False, requires `checksum` from a prior `validate_only=True` call to commit the mutation.
        checksum: Checksum of the validated operation returned by a prior `validate_only=True` call. Required when `validate_only=False`.
    """
    cleaned_customer_id = utils.clean_customer_id(customer_id)
    if not cleaned_customer_id:
        raise ToolError("Error: 'customer_id' must contain digits.")

    op_upper = (
        operation.value
        if isinstance(operation, Enum)
        else str(operation).upper()
    )
    type_upper = (
        association_type.value
        if isinstance(association_type, Enum)
        else str(association_type).upper()
    )

    if op_upper not in AssociationOperation.__members__:
        raise ToolError(
            f"Error: Invalid operation '{operation}'. Must be CREATE or REMOVE."
        )

    config = ASSOCIATION_CONFIGS.get(type_upper)
    if not config:
        valid_types = ", ".join(ASSOCIATION_CONFIGS)
        raise ToolError(
            f"Error: Invalid association_type '{association_type}'. Must be one of: {valid_types}."
        )

    ga_client = utils.get_googleads_client(login_customer_id=login_customer_id)
    service = utils.get_googleads_service_from_client(
        ga_client, config["service"]
    )
    op = ga_client.get_type(config["operation"])

    resource_name: str | None = None
    label_resource_name: str | None = None
    target_rn: str | None = None
    resolved_resource_id = resource_id

    if (
        type_upper == AssociationType.CUSTOMER.value
        and not resolved_resource_id
        and not association_resource_name
    ):
        resolved_resource_id = cleaned_customer_id

    if op_upper == "CREATE":
        if not resolved_resource_id:
            raise ToolError(
                f"Error: 'resource_id' is required to CREATE a {type_upper} label association."
            )
        if not label_id:
            raise ToolError(
                "Error: 'label_id' is required to CREATE a label association."
            )

        resolved_resource_id = _validate_resource_id_for_type(
            type_upper, resolved_resource_id
        )
        entity_prefix = config["entity_prefix"]

        if type_upper == AssociationType.CUSTOMER.value:
            resource_name = f"customers/{resolved_resource_id}"
        else:
            resource_name = f"customers/{cleaned_customer_id}/{entity_prefix}/{resolved_resource_id}"

        label_resource_name = (
            f"customers/{cleaned_customer_id}/labels/{label_id}"
        )
        target_rn = _construct_association_resource_name(
            cleaned_customer_id, type_upper, resolved_resource_id, label_id
        )

        association = op.create
        setattr(association, config["resource_field"], resource_name)
        setattr(association, config["label_field"], label_resource_name)

    elif op_upper == "REMOVE":
        if association_resource_name:
            expected_prefix = (
                f"customers/{cleaned_customer_id}/{config['resource_prefix']}/"
            )
            if not association_resource_name.startswith(expected_prefix):
                raise ToolError(
                    f"Error: 'association_resource_name' must start with '{expected_prefix}' "
                    "(or provide 'resource_id' and 'label_id' instead)."
                )
            target_rn = association_resource_name
        else:
            if not resolved_resource_id or not label_id:
                raise ToolError(
                    "Error: For REMOVE operation, you must provide either "
                    "'association_resource_name' OR both 'resource_id' and 'label_id'."
                )
            resolved_resource_id = _validate_resource_id_for_type(
                type_upper, resolved_resource_id
            )
            target_rn = _construct_association_resource_name(
                cleaned_customer_id,
                type_upper,
                resolved_resource_id,
                label_id,
            )

        op.remove = target_rn

    mutate_method = getattr(service, config["mutate_method"])

    operation_payload = {
        "tool": "manage_label_associations",
        "operation": op_upper,
        "association_type": type_upper,
        "resource_id": resolved_resource_id,
        "label_id": label_id,
        "association_resource_name": association_resource_name,
        "target_resource_name": target_rn,
    }

    change_items = pac.build_change_items(
        operation=op_upper,
        entity_readable=f"{type_upper} Label Association",
        primary_key_readable=target_rn or "",
        fields={
            "Association Type": type_upper,
            "Resource": resource_name,
            "Label": label_resource_name,
            "Association Resource Name": target_rn,
        },
    )

    request = ga_client.get_type(config["request"])
    request.customer_id = cleaned_customer_id
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

    return pac.propose_and_confirm(
        customer_id=cleaned_customer_id,
        validate_only=validate_only,
        checksum=checksum,
        operation_payload=operation_payload,
        change_items=change_items,
        validate_fn=_validate,
        commit_fn=_commit,
        error_prefix=f"Failed to {op_upper.lower()} {type_upper} label association",
    )
