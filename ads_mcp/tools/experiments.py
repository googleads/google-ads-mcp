# Copyright 2026 ReBattery.
# SPDX-License-Identifier: Apache-2.0

"""Tools for staged Google Ads campaign experiments."""

from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.tools.campaigns import _customer_id, _resource_name


experiments_mcp = FastMCP("experiments")


def _confirmed(confirm: bool) -> None:
    if not confirm:
        raise ValueError("Set confirm=true to perform this spend-affecting experiment action.")


@experiments_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def create_search_experiment_draft(
    customer_id: str, base_campaign_id: str, name: str
) -> dict[str, str]:
    """Create a SEARCH_CUSTOM experiment and its control/treatment arms.

    The experiment is left unscheduled. Google creates the treatment campaign
    from the control campaign; use the returned resource name for an explicit,
    confirmed schedule action after reviewing the treatment configuration.
    """
    customer_id = _customer_id(customer_id)
    if not base_campaign_id.isdigit() or not name.strip():
        raise ValueError("base_campaign_id and name are required.")
    client = utils.get_googleads_client()
    experiment_operation = client.get_type("ExperimentOperation")
    experiment = experiment_operation.create
    experiment.name = name.strip()
    experiment.type_ = "SEARCH_CUSTOM"
    experiment_name = _resource_name(
        client.get_service("ExperimentService").mutate_experiments(
            customer_id=customer_id, operations=[experiment_operation]
        ),
        "experiment",
    )

    campaign_name = client.get_service("CampaignService").campaign_path(
        customer_id, base_campaign_id
    )
    control_operation = client.get_type("ExperimentArmOperation")
    control = control_operation.create
    control.name = f"{name.strip()} control"
    control.experiment = experiment_name
    control.control = True
    control.campaigns.append(campaign_name)

    treatment_operation = client.get_type("ExperimentArmOperation")
    treatment = treatment_operation.create
    treatment.name = f"{name.strip()} treatment"
    treatment.experiment = experiment_name
    treatment.control = False

    arm_response = client.get_service("ExperimentArmService").mutate_experiment_arms(
        customer_id=customer_id, operations=[control_operation, treatment_operation]
    )
    return {
        "status": "DRAFT_NOT_SCHEDULED",
        "experiment": experiment_name,
        "control_arm": arm_response.results[0].resource_name,
        "treatment_arm": arm_response.results[1].resource_name,
    }


@experiments_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def schedule_experiment(customer_id: str, experiment_resource_name: str, confirm: bool = False) -> dict[str, str]:
    """Schedule an experiment after explicit confirmation. This can begin spending."""
    _confirmed(confirm)
    client = utils.get_googleads_client()
    client.get_service("ExperimentService").schedule_experiment(
        resource_name=experiment_resource_name
    )
    return {"status": "SCHEDULED", "experiment": experiment_resource_name, "customer_id": _customer_id(customer_id)}


@experiments_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def end_experiment(customer_id: str, experiment_resource_name: str, confirm: bool = False) -> dict[str, str]:
    """End an experiment after explicit confirmation."""
    _confirmed(confirm)
    client = utils.get_googleads_client()
    client.get_service("ExperimentService").end_experiment(
        resource_name=experiment_resource_name
    )
    return {"status": "ENDED", "experiment": experiment_resource_name, "customer_id": _customer_id(customer_id)}
