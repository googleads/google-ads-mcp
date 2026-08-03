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

"""Read-only Keyword Planner tools (Phase 1).

Exposes the Google Ads Keyword Planner "generate/list" methods that do not
persist anything in the account, keeping this server read-only:

  * KeywordPlanIdeaService.GenerateKeywordIdeas
  * KeywordPlanIdeaService.GenerateKeywordHistoricalMetrics
  * ReachPlanService.ListPlannableLocations
  * ReachPlanService.ListPlannableProducts
  * AudienceInsightsService.ListAudienceInsightsAttributes
  * AudienceInsightsService.ListInsightsEligibleDates
"""

import functools
from typing import Any, Callable, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException

import ads_mcp.utils as utils

keyword_planner_mcp = FastMCP("keyword_planner")


def _translate_google_ads_errors(func: Callable) -> Callable:
    """Wraps a tool so GoogleAdsException surfaces as a readable ToolError.

    Mirrors the error handling used by the `search` tool so failures reach the
    model as actionable messages instead of raw stack traces.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except GoogleAdsException as ex:
            error_msgs = [
                f"Google Ads API Error: {error.message}"
                for error in ex.failure.errors
            ]
            raise ToolError(
                f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs)
            )

    return wrapper


def _to_geo_resource(value: str) -> str:
    """Normalizes a geo target into a resource name.

    Accepts either a bare criterion id ('2276') or a full resource name
    ('geoTargetConstants/2276') and always returns the resource name form.
    """
    trimmed = value.strip()
    return f"geoTargetConstants/{trimmed}" if trimmed.isdigit() else trimmed


def _to_language_resource(value: str) -> str:
    """Normalizes a language into a resource name.

    Accepts either a bare criterion id ('1001') or a full resource name
    ('languageConstants/1001') and always returns the resource name form.
    """
    trimmed = value.strip()
    return f"languageConstants/{trimmed}" if trimmed.isdigit() else trimmed


def _format_results(results: Any) -> List[Dict[str, Any]]:
    """Converts an iterable of proto messages into a list of plain dicts."""
    return [utils.format_output_value(result) for result in results]


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def generate_keyword_ideas(
    customer_id: str,
    geo_target_constants: List[str],
    language: str,
    keywords: List[str] = [],
    page_url: str | None = None,
    keyword_plan_network: str = "GOOGLE_SEARCH",
    include_adult_keywords: bool = False,
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    """Generates keyword ideas with historical metrics (search volume, competition, CPC bid ranges).

    Provide at least one seed: `keywords`, a `page_url`, or both.

    ### customer_id
        A string of digits without punctuation (e.g. '1234567890', not '123-456-7890').

    ### geo_target_constants / language
        Pass Google Ads criterion ids ('2276', '1001') or full resource names
        ('geoTargetConstants/2276', 'languageConstants/1001'). Both forms are accepted.
        To look up ids, use the `search` tool on the `geo_target_constant` and
        `language_constant` resources.

    ### keyword_plan_network
        One of 'GOOGLE_SEARCH' or 'GOOGLE_SEARCH_AND_PARTNERS'.

    Args:
        customer_id: The id of the customer.
        geo_target_constants: One or more geo targets to scope metrics to.
        language: The language to scope metrics to.
        keywords: Seed keywords to expand from.
        page_url: A seed landing page URL to derive ideas from.
        keyword_plan_network: Which network the metrics apply to.
        include_adult_keywords: Whether to include adult keywords in the results.
        limit: Maximum number of ideas to return (client-side cap).
    """
    if not keywords and not page_url:
        raise ToolError(
            "Provide at least one seed: 'keywords', 'page_url', or both."
        )

    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = utils.get_googleads_type("GenerateKeywordIdeasRequest")

    request.customer_id = customer_id
    request.language = _to_language_resource(language)
    request.geo_target_constants.extend(
        _to_geo_resource(geo) for geo in geo_target_constants
    )
    request.keyword_plan_network = keyword_plan_network
    request.include_adult_keywords = include_adult_keywords

    if keywords and page_url:
        request.keyword_and_url_seed.url = page_url
        request.keyword_and_url_seed.keywords.extend(keywords)
    elif keywords:
        request.keyword_seed.keywords.extend(keywords)
    else:
        request.url_seed.url = page_url

    response = service.generate_keyword_ideas(request=request)

    ideas: List[Dict[str, Any]] = []
    for index, result in enumerate(response):
        if limit is not None and index >= limit:
            break
        ideas.append(utils.format_output_value(result))
    return ideas


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def generate_keyword_historical_metrics(
    customer_id: str,
    keywords: List[str],
    geo_target_constants: List[str],
    language: str,
    keyword_plan_network: str = "GOOGLE_SEARCH",
    include_adult_keywords: bool = False,
) -> List[Dict[str, Any]]:
    """Returns historical metrics (search volume, competition, CPC bid ranges) for specific keywords.

    Unlike `generate_keyword_ideas`, this does not expand seeds; it reports
    metrics for exactly the keywords you pass.

    See `generate_keyword_ideas` for the accepted `customer_id`,
    `geo_target_constants`, `language`, and `keyword_plan_network` formats.

    Args:
        customer_id: The id of the customer.
        keywords: The exact keywords to fetch metrics for.
        geo_target_constants: One or more geo targets to scope metrics to.
        language: The language to scope metrics to.
        keyword_plan_network: Which network the metrics apply to.
        include_adult_keywords: Whether to include adult keywords in the results.
    """
    service = utils.get_googleads_service("KeywordPlanIdeaService")
    request = utils.get_googleads_type(
        "GenerateKeywordHistoricalMetricsRequest"
    )

    request.customer_id = customer_id
    request.keywords.extend(keywords)
    request.language = _to_language_resource(language)
    request.geo_target_constants.extend(
        _to_geo_resource(geo) for geo in geo_target_constants
    )
    request.keyword_plan_network = keyword_plan_network
    request.include_adult_keywords = include_adult_keywords

    response = service.generate_keyword_historical_metrics(request=request)
    return _format_results(response.results)


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def list_plannable_locations() -> List[Dict[str, Any]]:
    """Lists locations that can be used for reach forecasting (ReachPlanService).

    Returns location ids and names to use as `plannable_location_id` for
    `list_plannable_products`.
    """
    service = utils.get_googleads_service("ReachPlanService")
    request = utils.get_googleads_type("ListPlannableLocationsRequest")

    response = service.list_plannable_locations(request=request)
    return _format_results(response.plannable_locations)


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def list_plannable_products(
    plannable_location_id: str,
) -> List[Dict[str, Any]]:
    """Lists ad products available for reach forecasting in a given location.

    Args:
        plannable_location_id: A location id from `list_plannable_locations`.
    """
    service = utils.get_googleads_service("ReachPlanService")
    request = utils.get_googleads_type("ListPlannableProductsRequest")
    request.plannable_location_id = plannable_location_id

    response = service.list_plannable_products(request=request)
    return _format_results(response.product_metadata)


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def list_audience_insights_attributes(
    customer_id: str,
    dimensions: List[str],
    query_text: str,
    customer_insights_group: str = "google-ads-mcp",
) -> List[Dict[str, Any]]:
    """Searches for audience attributes (interests, demographics, entities, locations) by free text.

    Use the returned attributes as building blocks for audience analysis.

    ### dimensions
        One or more of: 'KNOWLEDGE_GRAPH', 'GEO_TARGET_COUNTRY',
        'SUB_COUNTRY_LOCATION', 'YOUTUBE_CHANNEL', 'AFFINITY_USER_INTEREST',
        'IN_MARKET_USER_INTEREST', 'PARENTAL_STATUS', 'INCOME_RANGE',
        'AGE_RANGE', 'GENDER', 'DEVICE'.

    Args:
        customer_id: The id of the customer (digits only, no punctuation).
        dimensions: Which attribute dimensions to search within.
        query_text: The free-text term to search for (e.g. 'running shoes').
        customer_insights_group: A label used to group insights requests. This is
            a required API field; a default is provided.
    """
    service = utils.get_googleads_service("AudienceInsightsService")
    request = utils.get_googleads_type("ListAudienceInsightsAttributesRequest")

    request.customer_id = customer_id
    request.customer_insights_group = customer_insights_group
    request.dimensions = dimensions
    request.query_text = query_text

    response = service.list_audience_insights_attributes(request=request)
    return _format_results(response.attributes)


@keyword_planner_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@_translate_google_ads_errors
def list_insights_eligible_dates() -> Dict[str, Any]:
    """Returns the date ranges for which audience insights data is available.

    Useful to pick a valid reporting period before requesting insights.
    """
    service = utils.get_googleads_service("AudienceInsightsService")
    request = utils.get_googleads_type("ListInsightsEligibleDatesRequest")

    response = service.list_insights_eligible_dates(request=request)
    return utils.format_output_value(response)
