"""Keyword Quality Score, efficiency, and keyword-level performance report."""

from typing import Any, Dict, List, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_keyword_quality_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    min_quality_score: Optional[int] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Returns keyword-level Quality Score components and efficiency metrics.

    Quality Score (1–10) is Google's rating of keyword relevance. It affects Ad Rank
    and CPC. This tool surfaces the three QS components so you can identify which
    dimension is dragging a keyword's score down.

    Note on Ad Rank: Google does not expose Ad Rank as a direct field. Use
    quality_score combined with search_rank_lost_impression_share as a proxy —
    a low QS with high rank-lost IS indicates Ad Rank is limiting performance.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        campaign_id: Optional. Filter to a single campaign.
        ad_group_id: Optional. Filter to a single ad group.
        min_quality_score: Optional. Only return keywords at or below this score (e.g. 5 to find weak keywords).
        limit: Maximum rows to return (default 500).

    Returns:
        List of rows with:
        - keyword: keyword text
        - match_type: BROAD, PHRASE, EXACT
        - status: ENABLED, PAUSED, REMOVED
        - quality_score: overall QS (1–10), null if not enough data
        - creative_quality_score: ad relevance component (BELOW_AVERAGE / AVERAGE / ABOVE_AVERAGE)
        - post_click_quality_score: landing page experience component
        - search_predicted_ctr: expected CTR component
        - impressions, clicks, ctr, cost_micros, conversions, cost_per_conversion
        - search_rank_lost_impression_share: IS lost due to Ad Rank (Ad Rank proxy)
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
        "ad_group_criterion.quality_info.quality_score",
        "ad_group_criterion.quality_info.creative_quality_score",
        "ad_group_criterion.quality_info.post_click_quality_score",
        "ad_group_criterion.quality_info.search_predicted_ctr",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.cost_per_conversion",
        "metrics.search_rank_lost_impression_share",
        "metrics.search_impression_share",
    ]

    # keyword_view supports both quality_info attributes and performance metrics
    # together with segments.date. ad_group_criterion does not support metrics.
    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "ad_group_criterion.type = 'KEYWORD'",
        "ad_group_criterion.status != 'REMOVED'",
    ]
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")
    if ad_group_id:
        conditions.append(f"ad_group.id = {ad_group_id}")
    if min_quality_score is not None:
        conditions.append(f"ad_group_criterion.quality_info.quality_score <= {min_quality_score}")
        conditions.append("ad_group_criterion.quality_info.quality_score > 0")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM keyword_view"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY ad_group_criterion.quality_info.quality_score ASC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_keyword_quality_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                crit = row.ad_group_criterion
                qi = crit.quality_info
                m = row.metrics
                rows.append({
                    "campaign_name": row.campaign.name,
                    "ad_group_name": row.ad_group.name,
                    "keyword": crit.keyword.text,
                    "match_type": crit.keyword.match_type.name,
                    "status": crit.status.name,
                    "quality_score": qi.quality_score if qi.quality_score > 0 else None,
                    "creative_quality_score": qi.creative_quality_score.name,
                    "post_click_quality_score": qi.post_click_quality_score.name,
                    "search_predicted_ctr": qi.search_predicted_ctr.name,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "cost_per_conversion": round(m.cost_per_conversion, 2),
                    "search_impression_share": round(m.search_impression_share, 4),
                    "search_rank_lost_impression_share": round(m.search_rank_lost_impression_share, 4),
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
