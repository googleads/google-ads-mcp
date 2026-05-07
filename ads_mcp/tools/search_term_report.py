"""Search Term Report tool for negative keyword discovery."""

from typing import Any, Dict, List, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_search_term_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    min_impressions: int = 10,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Returns search terms that triggered ads, for negative keyword discovery.

    Each row includes the search term, its current status (ADDED/EXCLUDED/NONE),
    the triggering keyword and match type, and key performance metrics.
    Sorted by cost descending so the highest-spend wasted terms surface first.

    Args:
        customer_id: Client account ID (digits only, e.g. "1635583349").
        start_date: Start of date range in YYYY-MM-DD format.
        end_date: End of date range in YYYY-MM-DD format.
        campaign_id: Optional campaign ID to narrow results.
        ad_group_id: Optional ad group ID to narrow results.
        min_impressions: Minimum impressions to filter out noise (default 10).
        limit: Maximum rows to return (default 200).

    Returns:
        List of rows, each containing:
        - search_term: The actual query the user typed.
        - status: ADDED (already a keyword), EXCLUDED (already a negative), NONE (not added yet).
        - triggering_keyword: The keyword that matched this query.
        - match_type: BROAD, PHRASE, or EXACT.
        - impressions: Total impressions in the date range.
        - clicks: Total clicks.
        - ctr: Click-through rate (0.0 – 1.0).
        - cost_micros: Total cost in micros (divide by 1,000,000 for currency value).
        - conversions: Total conversions.
        - top_impression_pct: Fraction of impressions in top position.
        - abs_top_impression_pct: Fraction of impressions in absolute top position.
    """
    ga_service = utils.get_googleads_service("GoogleAdsService")

    fields = [
        "search_term_view.search_term",
        "search_term_view.status",
        "segments.keyword.info.match_type",
        "segments.keyword.info.text",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.top_impression_percentage",
        "metrics.absolute_top_impression_percentage",
    ]

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        f"metrics.impressions >= {min_impressions}",
    ]

    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")

    if ad_group_id:
        conditions.append(f"ad_group.id = {ad_group_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM search_term_view"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.cost_micros DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_search_term_report query: {query}")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                stv = row.search_term_view
                kw = row.segments.keyword.info
                m = row.metrics
                rows.append({
                    "search_term": stv.search_term,
                    "status": stv.status.name,
                    "triggering_keyword": kw.text,
                    "match_type": kw.match_type.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "top_impression_pct": round(m.top_impression_percentage, 4),
                    "abs_top_impression_pct": round(m.absolute_top_impression_percentage, 4),
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
