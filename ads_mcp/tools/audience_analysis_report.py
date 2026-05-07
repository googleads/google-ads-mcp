"""Audience analysis report — performance broken down by audience segment."""

from typing import Any, Dict, List, Literal, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_audience_analysis_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    level: Literal["campaign", "ad_group"] = "ad_group",
    campaign_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Returns performance metrics broken down by audience segment (user lists, in-market,
    affinity, etc.) at campaign or ad group level.

    Each row represents one audience criterion and its performance within that campaign
    or ad group. Use this to identify which audience segments drive the most conversions
    or have the best CTR.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        level: "campaign" or "ad_group" (default "ad_group").
        campaign_id: Optional. Filter to a single campaign.
        limit: Maximum rows to return (default 200).

    Returns:
        List of rows with:
        - campaign_name, campaign_id
        - ad_group_name (at ad_group level)
        - audience_type: type of criterion (USER_LIST, USER_INTEREST, etc.)
        - impressions, clicks, ctr, cost_micros, conversions, cost_per_conversion
        - top_impression_pct, abs_top_impression_pct
    """
    resource = "campaign_audience_view" if level == "campaign" else "ad_group_audience_view"

    fields = [
        "campaign.name",
        "campaign.id",
        "ad_group_criterion.type",
        "ad_group_criterion.status",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.cost_per_conversion",
        "metrics.top_impression_percentage",
        "metrics.absolute_top_impression_percentage",
    ]

    if level == "ad_group":
        fields.insert(2, "ad_group.name")
        fields.insert(3, "ad_group.id")

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "metrics.impressions > 0",
        "ad_group_criterion.status != 'REMOVED'",
    ]
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM {resource}"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.conversions DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_audience_analysis_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                crit = row.ad_group_criterion
                entry: Dict[str, Any] = {
                    "campaign_name": row.campaign.name,
                    "campaign_id": str(row.campaign.id),
                    "audience_type": crit.type_.name,
                    "status": crit.status.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "cost_per_conversion": round(m.cost_per_conversion, 2),
                    "top_impression_pct": round(m.top_impression_percentage, 4),
                    "abs_top_impression_pct": round(m.absolute_top_impression_percentage, 4),
                }
                if level == "ad_group":
                    entry["ad_group_name"] = row.ad_group.name
                    entry["ad_group_id"] = str(row.ad_group.id)
                rows.append(entry)
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
