"""Product catalog report — shopping performance by product dimension."""

from typing import Any, Dict, List, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_google_product_catalog_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    campaign_id: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Returns Shopping campaign performance broken down by product attributes
    (brand, category, product type, custom labels, item ID).

    Each row is one product / product group combination with its performance metrics
    and impression share data.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        campaign_id: Optional. Filter to a single Shopping campaign.
        limit: Maximum rows to return (default 500).

    Returns:
        List of rows with:
        - campaign_name, campaign_id
        - product_brand, product_type, product_category, product_item_id
        - custom_label_0 through custom_label_4
        - impressions, clicks, ctr, cost_micros, conversions
        - search_impression_share: IS for this product
        - search_budget_lost_impression_share
        - search_rank_lost_impression_share
    """
    fields = [
        "campaign.name",
        "campaign.id",
        "segments.product_brand",
        "segments.product_type_l1",
        "segments.product_category_level1",
        "segments.product_item_id",
        "segments.product_custom_attribute0",
        "segments.product_custom_attribute1",
        "segments.product_custom_attribute2",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.conversions_value",
        "metrics.cost_per_conversion",
        "metrics.search_impression_share",
        "metrics.search_budget_lost_impression_share",
        "metrics.search_rank_lost_impression_share",
    ]

    conditions = [
        f"segments.date BETWEEN '{start_date}' AND '{end_date}'",
        "metrics.impressions > 0",
    ]
    if campaign_id:
        conditions.append(f"campaign.id = {campaign_id}")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM shopping_performance_view"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY metrics.cost_micros DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_google_product_catalog_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                seg = row.segments
                rows.append({
                    "campaign_name": row.campaign.name,
                    "campaign_id": str(row.campaign.id),
                    "product_brand": seg.product_brand,
                    "product_type": seg.product_type_l1,
                    "product_category": seg.product_category_level1,
                    "product_item_id": seg.product_item_id,
                    "custom_label_0": seg.product_custom_attribute0,
                    "custom_label_1": seg.product_custom_attribute1,
                    "custom_label_2": seg.product_custom_attribute2,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": round(m.ctr, 4),
                    "cost_micros": m.cost_micros,
                    "conversions": round(m.conversions, 2),
                    "conversions_value": round(m.conversions_value, 2),
                    "cost_per_conversion": round(m.cost_per_conversion, 2),
                    "search_impression_share": round(m.search_impression_share, 4),
                    "search_budget_lost_impression_share": round(m.search_budget_lost_impression_share, 4),
                    "search_rank_lost_impression_share": round(m.search_rank_lost_impression_share, 4),
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
