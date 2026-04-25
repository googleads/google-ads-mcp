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

"""Experiment tools (Search campaign A/B tests).

High-level flow:

  1. create_experiment(name, type='SEARCH_CUSTOM') — creates the experiment shell.
  2. create_experiment_arm(experiment_id, name='Control', control=True,
        campaigns=[base_campaign_id])
  3. create_experiment_arm(experiment_id, name='Treatment',
        traffic_split=50, campaigns=[])  — the API auto-creates a draft campaign
        on the fly once scheduled; or pass a pre-built draft campaign id.
  4. schedule_experiment(experiment_id, start_date, end_date) — the API creates
        draft campaigns for the treatment arm and starts serving on the
        scheduled date.
  5. After it runs: graduate_experiment (promote treatment to a full campaign)
     OR end_experiment (stop early).
"""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


def _experiment_path(customer_id: str, experiment_id: str | int) -> str:
    return f"customers/{customer_id}/experiments/{experiment_id}"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_experiments(
    customer_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    """Lists experiments in the account."""
    query = (
        "SELECT experiment.resource_name, experiment.experiment_id, "
        "experiment.name, experiment.description, experiment.type, "
        "experiment.status, experiment.start_date, experiment.end_date "
        f"FROM experiment LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_experiment(
    customer_id: str,
    name: str,
    experiment_type: str = "SEARCH_CUSTOM",
    description: str | None = None,
    suffix: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates an experiment (the shell — arms are added separately).

    Args:
        experiment_type: 'SEARCH_CUSTOM' for Search A/B tests. Other values
            include 'DISPLAY_AUTOMATED_BIDDING_STRATEGY',
            'YOUTUBE_CUSTOM', 'HOTEL_CUSTOM'.
        suffix: Appended to auto-created draft campaign names (e.g. '[exp]').
    """
    client = utils.get_googleads_client()
    service = client.get_service("ExperimentService")
    op = client.get_type("ExperimentOperation")
    e = op.create
    e.name = name
    if description:
        e.description = description
    if suffix:
        e.suffix = suffix
    e.type_ = client.enums.ExperimentTypeEnum[experiment_type]

    with _common.google_ads_errors():
        response = service.mutate_experiments(
            request=_common.build_request(
                client, "MutateExperimentsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_experiment_arm(
    customer_id: str,
    experiment_id: str,
    name: str,
    control: bool = False,
    traffic_split: int = 50,
    base_campaign_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates an arm of an experiment.

    Args:
        control: True if this is the control arm (serves the original traffic).
        traffic_split: 1..100 — percentage of traffic this arm receives. For a
            50/50 test, set both arms to 50.
        base_campaign_ids: Campaign ids this arm acts on. For the control arm,
            these are the existing campaigns; for the treatment arm, the API
            creates draft variants.
    """
    client = utils.get_googleads_client()
    service = client.get_service("ExperimentArmService")
    op = client.get_type("ExperimentArmOperation")
    arm = op.create
    arm.experiment = _experiment_path(customer_id, experiment_id)
    arm.name = name
    arm.control = bool(control)
    arm.traffic_split = int(traffic_split)
    if base_campaign_ids:
        arm.campaigns.extend(
            [_common.campaign_path(customer_id, cid) for cid in base_campaign_ids]
        )

    with _common.google_ads_errors():
        response = service.mutate_experiment_arms(
            request=_common.build_request(
                client, "MutateExperimentArmsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True)
)
def schedule_experiment(
    customer_id: str,
    experiment_id: str,
    run_synchronously: bool = False,
) -> dict[str, Any]:
    """Schedules an experiment to start. Google copies the base campaigns into
    draft variants for the treatment arm, then begins split-testing at the
    experiment's start_date.

    Args:
        run_synchronously: True to wait for the long-running operation to
            complete before returning. Default False (returns immediately; poll
            via list_experiments for status).
    """
    client = utils.get_googleads_client()
    service = client.get_service("ExperimentService")
    with _common.google_ads_errors():
        lro = service.schedule_experiment(
            resource_name=_experiment_path(customer_id, experiment_id)
        )
        if run_synchronously:
            lro.result()
    return {
        "scheduled": True,
        "lro_name": lro.operation.name if lro.operation else None,
        "done": lro.done(),
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True)
)
def end_experiment(
    customer_id: str, experiment_id: str
) -> dict[str, Any]:
    """Ends a running experiment immediately (treatment campaigns are paused)."""
    client = utils.get_googleads_client()
    service = client.get_service("ExperimentService")
    with _common.google_ads_errors():
        service.end_experiment(
            experiment=_experiment_path(customer_id, experiment_id)
        )
    return {"ended": True, "experiment_id": experiment_id}


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def graduate_experiment(
    customer_id: str,
    experiment_id: str,
    campaign_budget_mappings: list[dict[str, str]],
) -> dict[str, Any]:
    """Graduates (promotes) an experiment's treatment campaigns into permanent campaigns.

    Args:
        campaign_budget_mappings: list of
            {'experiment_campaign_id': '...', 'campaign_budget_id': '...'}
            — each treatment campaign needs its own permanent budget.
    """
    client = utils.get_googleads_client()
    service = client.get_service("ExperimentService")
    mappings = []
    for m in campaign_budget_mappings:
        item = client.get_type("CampaignBudgetMapping")
        item.experiment_campaign = _common.campaign_path(
            customer_id, m["experiment_campaign_id"]
        )
        item.campaign_budget = _common.campaign_budget_path(
            customer_id, m["campaign_budget_id"]
        )
        mappings.append(item)
    with _common.google_ads_errors():
        service.graduate_experiment(
            experiment=_experiment_path(customer_id, experiment_id),
            campaign_budget_mappings=mappings,
        )
    return {"graduated": True, "experiment_id": experiment_id}
