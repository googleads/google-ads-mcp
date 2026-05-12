"""Impression Share, Lost IS (Budget/Rank), Top-of-page and Abs-top-of-page report."""

from typing import Any, Dict, List, Literal, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_google_impression_share_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    level: Literal["keyword", "ad_group", "campaign"] = "keyword",
    campaign_id: Optional[str] = None,
    ad_group_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Returns Impression Share, Lost IS (Budget), Lost IS (Rank), top-of-page and
    absolute-top-of-page metrics. Sorted by search impression share ascending so the
    weakest performers surface first.

    Note on date range: Google Ads IS metrics do NOT support segments.date at keyword
    level — this is a platform limitation. At keyword level start_date/end_date are
    ignored and IS reflects a recent rolling period. Date filtering works at ad_group
    and campaign level.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format. Used at ad_group/campaign level only.
        end_date: End date in YYYY-MM-DD format. Used at ad_group/campaign level only.
        level: Granularity — "keyword", "ad_group", or "campaign". Default "keyword".
        campaign_id: Optional. Filter to a single campaign.
        ad_group_id: Optional. Filter to a single ad group (only used at keyword/ad_group level).
        limit: Maximum rows to return (default 200).

    Returns:
        List of rows with:
        - entity: name of the keyword / ad group / campaign
        - match_type: BROAD, PHRASE, EXACT (keyword level only)
        - campaign_name, ad_group_name (where applicable)
        - search_impression_share: fraction of eligible impressions received (0.0–1.0)
        - search_budget_lost_impression_share: IS lost to budget
        - search_rank_lost_impression_share: IS lost to rank
        - search_absolute_top_impression_share: IS at absolute top position
        - search_budget_lost_absolute_top_impression_share
        - search_rank_lost_absolute_top_impression_share
        - top_impression_pct: fraction of impressions shown at top of page
        - abs_top_impression_pct: fraction of impressions at absolute top
        - impressions, clicks, cost_micros
    """
    resource_map = {
        "keyword": "keyword_view",
        "ad_group": "ad_group",
        "campaign": "campaign",
    }
    resource = resource_map[level]

    # keyword_view only supports base IS metrics — budget/rank lost variants are
    # unavailable at keyword level (Google Ads API limitation).
    keyword_metrics = [
        "metrics.search_impression_share",
        "metrics.search_exact_match_impression_share",
        "metrics.search_absolute_top_impression_share",
        "metrics.search_top_impression_share",
        "metrics.top_impression_percentage",
        "metrics.absolute_top_impression_percentage",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.cost_micros",
    ]

    # campaign and ad_group support the full IS set including budget/rank lost variants.
    full_metrics = keyword_metrics + [
        "metrics.search_budget_lost_impression_share",
        "metrics.search_rank_lost_impression_share",
        "metrics.search_budget_lost_absolute_top_impression_share",
        "metrics.search_rank_lost_absolute_top_impression_share",
        "metrics.search_budget_lost_top_impression_share",
        "metrics.search_rank_lost_top_impression_share",
    ]

    if level == "keyword":
        fields = [
            "campaign.name",
            "campaign.id",
            "ad_group.name",
            "ad_group.id",
            "ad_group_criterion.keyword.text",
            "ad_group_criterion.keyword.match_type",
            "ad_group_criterion.status",
        ] + keyword_metrics
    elif level == "ad_group":
        fields = [
            "campaign.name",
            "campaign.id",
            "ad_group.name",
            "ad_group.id",
            "ad_group.status",
        ] + full_metrics
    else:
        fields = [
            "campaign.name",
            "campaign.id",
            "campaign.status",
            "campaign.advertising_channel_type",
        ] + full_metrics

    conditions = ["metrics.impressions > 0"]

    # IS metrics do not support segments.date at keyword level (Google Ads API limitation).
    # Date segmentation is only supported at ad_group and campaign level.
    if level != "keyword":
        conditions.insert(0, f"segments.date BETWEEN '{start_date}' AND '{end_date}'")

    if level == "keyword":
        conditions.append("ad_group_criterion.type = 'KEYWORD'")
        conditions.append("ad_group_criterion.status != 'REMOVED'")
    if level in ("keyword", "ad_group") and campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")
    if level == "keyword" and ad_group_id:
        conditions.append(f"ad_group.id = {ad_group_id}")
    if level == "ad_group" and campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM {resource}"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.search_impression_share ASC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_google_impression_share_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                entry: Dict[str, Any] = {
                    "campaign_name": row.campaign.name,
                    "campaign_id": str(row.campaign.id),
                    "search_impression_share": round(m.search_impression_share, 4),
                    "search_exact_match_impression_share": round(m.search_exact_match_impression_share, 4),
                    "search_absolute_top_impression_share": round(m.search_absolute_top_impression_share, 4),
                    "search_top_impression_share": round(m.search_top_impression_share, 4),
                    "top_impression_pct": round(m.top_impression_percentage, 4),
                    "abs_top_impression_pct": round(m.absolute_top_impression_percentage, 4),
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "cost_micros": m.cost_micros,
                }
                if level == "keyword":
                    entry["ad_group_name"] = row.ad_group.name
                    entry["keyword"] = row.ad_group_criterion.keyword.text
                    entry["match_type"] = row.ad_group_criterion.keyword.match_type.name
                    entry["status"] = row.ad_group_criterion.status.name
                elif level == "ad_group":
                    entry["ad_group_name"] = row.ad_group.name
                    entry["ad_group_id"] = str(row.ad_group.id)
                    entry["status"] = row.ad_group.status.name
                    entry["search_budget_lost_impression_share"] = round(m.search_budget_lost_impression_share, 4)
                    entry["search_rank_lost_impression_share"] = round(m.search_rank_lost_impression_share, 4)
                    entry["search_budget_lost_absolute_top_impression_share"] = round(m.search_budget_lost_absolute_top_impression_share, 4)
                    entry["search_rank_lost_absolute_top_impression_share"] = round(m.search_rank_lost_absolute_top_impression_share, 4)
                else:
                    entry["status"] = row.campaign.status.name
                    entry["channel_type"] = row.campaign.advertising_channel_type.name
                    entry["search_budget_lost_impression_share"] = round(m.search_budget_lost_impression_share, 4)
                    entry["search_rank_lost_impression_share"] = round(m.search_rank_lost_impression_share, 4)
                    entry["search_budget_lost_absolute_top_impression_share"] = round(m.search_budget_lost_absolute_top_impression_share, 4)
                    entry["search_rank_lost_absolute_top_impression_share"] = round(m.search_rank_lost_absolute_top_impression_share, 4)
                rows.append(entry)
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
