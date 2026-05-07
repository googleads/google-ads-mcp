"""Auction Insights report — competitor overlap, outranking share, and position metrics."""

from typing import Any, Dict, List, Literal, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_auction_insights_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    level: Literal["keyword", "ad_group", "campaign"] = "campaign",
    campaign_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Returns Auction Insights metrics broken down by competitor domain.

    Shows how your ads compete with other advertisers in the same auctions.
    Each row is one competitor domain (segments.auction_insight_domain) within
    a campaign, ad group, or keyword.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        level: "keyword", "ad_group", or "campaign" (default "campaign").
        campaign_id: Optional. Filter to a single campaign.
        ad_group_id: Optional. Filter to a single ad group (only at keyword/ad_group level).
        limit: Maximum rows to return (default 200).

    Returns:
        List of rows with:
        - competitor_domain: the other advertiser's display URL domain
        - campaign_name (always present)
        - ad_group_name (at keyword / ad_group level)
        - keyword, match_type (at keyword level)
        - impression_share: competitor's IS in the same auctions
        - overlap_rate: fraction of your impressions where competitor also appeared
        - outranking_share: fraction of auctions where your ad ranked above theirs
        - position_above_rate: fraction of auctions where competitor ranked above you
        - top_impression_pct: competitor's top-of-page impression fraction
        - abs_top_impression_pct: competitor's absolute-top impression fraction
    """
    resource_map = {
        "keyword": "keyword_view",
        "ad_group": "ad_group",
        "campaign": "campaign",
    }
    resource = resource_map[level]

    auction_metrics = [
        "metrics.auction_insight_search_impression_share",
        "metrics.auction_insight_search_overlap_rate",
        "metrics.auction_insight_search_outranking_share",
        "metrics.auction_insight_search_position_above_rate",
        "metrics.auction_insight_search_top_impression_percentage",
        "metrics.auction_insight_search_absolute_top_impression_percentage",
        "segments.auction_insight_domain",
    ]

    if level == "keyword":
        fields = [
            "campaign.name",
            "ad_group.name",
            "ad_group_criterion.keyword.text",
            "ad_group_criterion.keyword.match_type",
        ] + auction_metrics
    elif level == "ad_group":
        fields = ["campaign.name", "ad_group.name"] + auction_metrics
    else:
        fields = ["campaign.name"] + auction_metrics

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "metrics.auction_insight_search_impression_share > 0",
    ]
    if level == "keyword":
        conditions.append("ad_group_criterion.type = 'KEYWORD'")
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")
    if ad_group_id and level in ("keyword", "ad_group"):
        conditions.append(f"ad_group.id = {ad_group_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM {resource}"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.auction_insight_search_impression_share DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_auction_insights_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                entry: Dict[str, Any] = {
                    "campaign_name": row.campaign.name,
                    "competitor_domain": row.segments.auction_insight_domain,
                    "impression_share": round(m.auction_insight_search_impression_share, 4),
                    "overlap_rate": round(m.auction_insight_search_overlap_rate, 4),
                    "outranking_share": round(m.auction_insight_search_outranking_share, 4),
                    "position_above_rate": round(m.auction_insight_search_position_above_rate, 4),
                    "top_impression_pct": round(m.auction_insight_search_top_impression_percentage, 4),
                    "abs_top_impression_pct": round(m.auction_insight_search_absolute_top_impression_percentage, 4),
                }
                if level in ("keyword", "ad_group"):
                    entry["ad_group_name"] = row.ad_group.name
                if level == "keyword":
                    entry["keyword"] = row.ad_group_criterion.keyword.text
                    entry["match_type"] = row.ad_group_criterion.keyword.match_type.name
                rows.append(entry)
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        combined = "\n".join(error_msgs)
        if "doesn't have access to metrics" in combined or "auction_insight" in combined:
            raise ToolError(
                "Auction Insights metrics require Standard Access on your Google Ads "
                "developer token. Apply at Google Ads → Tools → API Centre. "
                f"(Request ID: {ex.request_id})"
            )
        raise ToolError(f"Request ID: {ex.request_id}\n" + combined)
