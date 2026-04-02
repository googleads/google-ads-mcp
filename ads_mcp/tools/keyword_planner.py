"""Keyword Planner tools for search volume and keyword ideas."""

from typing import Any, Dict, List, Optional

from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


def generate_keyword_ideas(
    customer_id: str,
    keywords: Optional[List[str]] = None,
    page_url: Optional[str] = None,
    language_id: str = "1000",
    geo_target_ids: Optional[List[str]] = None,
    include_adult_keywords: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Generate keyword ideas with search volume and competition data.

    Uses the Google Ads KeywordPlanIdeaService to get keyword suggestions
    and historical metrics like monthly search volume and competition.

    Args:
        customer_id: The Google Ads customer ID (no hyphens, e.g. "1234567890").
        keywords: Seed keywords to generate ideas from. At least one of
            keywords or page_url must be provided.
        page_url: A URL to generate keyword ideas from. At least one of
            keywords or page_url must be provided.
        language_id: Language criterion ID. Default "1000" (English).
            Common values: 1000=English, 1003=Spanish, 1001=French,
            1009=Portuguese, 1005=German, 1004=Italian.
        geo_target_ids: List of geo target criterion IDs. Default ["2840"] (US).
            Common values: 2840=US, 2826=UK, 2124=Canada, 2036=Australia,
            2356=India, 2276=Germany, 2250=France, 2076=Brazil.
        include_adult_keywords: Whether to include adult keywords.
        limit: Maximum number of keyword ideas to return. Default 50.

    Returns:
        List of keyword idea dicts with fields: keyword, avg_monthly_searches,
        competition, competition_index, low_top_of_page_bid_micros,
        high_top_of_page_bid_micros, monthly_search_volumes.
    """
    if not keywords and not page_url:
        raise ValueError("At least one of 'keywords' or 'page_url' must be provided.")

    if geo_target_ids is None:
        geo_target_ids = ["2840"]

    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = utils.get_googleads_type("GenerateKeywordIdeasRequest")

    request.customer_id = customer_id
    request.language = f"languageConstants/{language_id}"
    request.include_adult_keywords = include_adult_keywords

    for geo_id in geo_target_ids:
        request.geo_target_constants.append(f"geoTargetConstants/{geo_id}")

    request.keyword_plan_network = utils.get_googleads_type(
        "KeywordPlanNetworkEnum"
    ).KeywordPlanNetwork.GOOGLE_SEARCH_AND_PARTNERS

    if keywords and page_url:
        seed = request.keyword_and_url_seed
        seed.url = page_url
        for kw in keywords:
            seed.keywords.append(kw)
    elif keywords:
        seed = request.keyword_seed
        for kw in keywords:
            seed.keywords.append(kw)
    elif page_url:
        request.url_seed.url = page_url

    results = []
    count = 0
    for idea in service.generate_keyword_ideas(request=request):
        if count >= limit:
            break

        metrics = idea.keyword_idea_metrics
        monthly_volumes = []
        if metrics.monthly_search_volumes:
            for mv in metrics.monthly_search_volumes:
                monthly_volumes.append({
                    "year": mv.year,
                    "month": mv.month.name if hasattr(mv.month, "name") else str(mv.month),
                    "monthly_searches": mv.monthly_searches,
                })

        results.append({
            "keyword": idea.text,
            "avg_monthly_searches": metrics.avg_monthly_searches,
            "competition": metrics.competition.name if hasattr(metrics.competition, "name") else str(metrics.competition),
            "competition_index": metrics.competition_index,
            "low_top_of_page_bid_micros": metrics.low_top_of_page_bid_micros,
            "high_top_of_page_bid_micros": metrics.high_top_of_page_bid_micros,
            "monthly_search_volumes": monthly_volumes[-12:] if monthly_volumes else [],
        })
        count += 1

    return results


_tool_description = """Generate keyword ideas with search volume and competition data.

Uses the Google Ads KeywordPlanIdeaService to get keyword suggestions
and historical metrics like monthly search volume and competition.

Args:
    customer_id: The Google Ads customer ID (no hyphens, e.g. "1234567890").
    keywords: Seed keywords to generate ideas from. At least one of
        keywords or page_url must be provided.
    page_url: A URL to generate keyword ideas from. At least one of
        keywords or page_url must be provided.
    language_id: Language criterion ID. Default "1000" (English).
        Common values: 1000=English, 1003=Spanish, 1001=French,
        1009=Portuguese, 1005=German, 1004=Italian.
    geo_target_ids: List of geo target criterion IDs. Default ["2840"] (US).
        Common values: 2840=US, 2826=UK, 2124=Canada, 2036=Australia,
        2356=India, 2276=Germany, 2250=France, 2076=Brazil.
    include_adult_keywords: Whether to include adult keywords.
    limit: Maximum number of keyword ideas to return. Default 50.

Returns:
    List of keyword idea dicts with fields: keyword, avg_monthly_searches,
    competition, competition_index, low_top_of_page_bid_micros,
    high_top_of_page_bid_micros, monthly_search_volumes.
"""

mcp.add_tool(
    generate_keyword_ideas,
    title="Generate Keyword Ideas",
    description=_tool_description,
)
