"""Reach & Frequency report and audience size / overlap math for TAM estimation."""

from typing import Any, Dict, List, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_google_reach_frequency_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Returns impressions and frequency metrics per campaign.

    True reach (unique users) is only available for Video and Display campaigns
    in Google Ads. For Search campaigns this tool returns impressions and
    average frequency derived from impression data instead.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        campaign_id: Optional. Filter to a single campaign.
        limit: Maximum rows to return (default 200).

    Returns:
        List of rows with:
        - campaign_name, campaign_id
        - channel_type: SEARCH, DISPLAY, VIDEO, etc.
        - impressions
        - clicks, ctr
        - cost_micros
        - conversions
        Note: Frequency is not a GAQL metric for Search campaigns.
        For Video/Display, use the reach_plan_cell resource for forecasting.
    """
    fields = [
        "campaign.name",
        "campaign.id",
        "campaign.advertising_channel_type",
        "campaign.status",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.cost_per_conversion",
    ]

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "metrics.impressions > 0",
        "campaign.status != 'REMOVED'",
    ]
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM campaign"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.impressions DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_google_reach_frequency_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                rows.append({
                    "campaign_name": row.campaign.name,
                    "campaign_id": str(row.campaign.id),
                    "channel_type": row.campaign.advertising_channel_type.name,
                    "status": row.campaign.status.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "cost_per_conversion": round(m.cost_per_conversion, 2),
                    "note": "Frequency (unique reach) is only available for Video/Display via reach_plan_cell resource.",
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_google_audience_overlap_estimate(
    customer_id: str,
    audience_ids: List[str],
) -> Dict[str, Any]:
    """Returns the size of each audience (user list) and an estimated union size.

    Google Ads does not expose true audience overlap data via GAQL. This tool
    fetches individual audience sizes and computes a conservative union estimate
    using the inclusion-exclusion principle with an assumed 20% pairwise overlap.
    Use this as a rough TAM proxy — not an exact figure.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        audience_ids: List of user_list resource IDs (digits only, e.g. ["123456", "789012"]).

    Returns:
        - audiences: list of {id, name, size_for_search, size_range_for_search, eligible_for_search}
        - estimated_union_search: rough estimate of combined unique audience for search
        - note: explanation of the estimation method
    """
    fields = [
        "user_list.id",
        "user_list.name",
        "user_list.size_for_search",
        "user_list.size_range_for_search",
        "user_list.size_for_display",
        "user_list.size_range_for_display",
        "user_list.eligible_for_search",
        "user_list.type",
    ]

    id_list = ", ".join(audience_ids)
    conditions = [f"user_list.id IN ({id_list})"]

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM user_list"
        f" WHERE {' AND '.join(conditions)}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_google_audience_overlap_estimate query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        audiences = []
        total_size = 0
        for batch in response:
            for row in batch.results:
                ul = row.user_list
                size = ul.size_for_search
                audiences.append({
                    "id": str(ul.id),
                    "name": ul.name,
                    "type": ul.type_.name,
                    "size_for_search": size,
                    "size_range_for_search": ul.size_range_for_search.name,
                    "size_for_display": ul.size_for_display,
                    "size_range_for_display": ul.size_range_for_display.name,
                    "eligible_for_search": ul.eligible_for_search,
                })
                total_size += size

        # Conservative union estimate: subtract 20% assumed pairwise overlap per additional audience
        n = len(audiences)
        if n <= 1:
            estimated_union = audiences[0]["size_for_search"] if audiences else 0
        else:
            overlap_factor = 1 - (0.20 * (n - 1) / n)
            estimated_union = int(total_size * max(overlap_factor, 0.5))

        return {
            "audiences": audiences,
            "estimated_union_search": estimated_union,
            "note": (
                "Union is estimated using 20% assumed pairwise overlap. "
                "Google Ads does not expose true overlap data via GAQL. "
                "Treat this as a rough upper bound for TAM estimation."
            ),
        }
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
