"""Keywords report — full keyword list with bids, status, and efficiency metrics."""

from typing import Any, Dict, List, Literal, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_keyword_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    status: Literal["ENABLED", "PAUSED", "ALL"] = "ENABLED",
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Returns all keywords with their bids, match types, status, and performance metrics.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        campaign_id: Optional. Filter to a single campaign.
        ad_group_id: Optional. Filter to a single ad group.
        status: "ENABLED", "PAUSED", or "ALL" (default "ENABLED").
        limit: Maximum rows to return (default 1000).

    Returns:
        List of rows with:
        - keyword: keyword text
        - match_type: BROAD, PHRASE, EXACT
        - status: ENABLED or PAUSED
        - cpc_bid_micros: max CPC bid set on the keyword (0 if using ad group default)
        - quality_score: QS (1–10)
        - impressions, clicks, ctr, cost_micros, conversions, cost_per_conversion
        - search_impression_share
        - campaign_name, ad_group_name
    """
    fields = [
        "campaign.name",
        "campaign.id",
        "ad_group.name",
        "ad_group.id",
        "ad_group_criterion.keyword.text",
        "ad_group_criterion.keyword.match_type",
        "ad_group_criterion.status",
        "ad_group_criterion.cpc_bid_micros",
        "ad_group_criterion.quality_info.quality_score",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.cost_per_conversion",
        "metrics.search_impression_share",
    ]

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "ad_group_criterion.type = 'KEYWORD'",
        "ad_group_criterion.status != 'REMOVED'",
    ]
    if status != "ALL":
        conditions.append(f"ad_group_criterion.status = '{status}'")
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")
    if ad_group_id:
        conditions.append(f"ad_group.id = {ad_group_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM keyword_view"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.cost_micros DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_keyword_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                crit = row.ad_group_criterion
                m = row.metrics
                qs = crit.quality_info.quality_score
                rows.append({
                    "campaign_name": row.campaign.name,
                    "ad_group_name": row.ad_group.name,
                    "keyword": crit.keyword.text,
                    "match_type": crit.keyword.match_type.name,
                    "status": crit.status.name,
                    "cpc_bid_micros": crit.cpc_bid_micros,
                    "quality_score": qs if qs > 0 else None,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "cost_per_conversion": round(m.cost_per_conversion, 2),
                    "search_impression_share": round(m.search_impression_share, 4),
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
