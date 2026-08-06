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

import datetime
import functools
from typing import Any, Callable, Dict, List, Tuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from google.ads.googleads.errors import GoogleAdsException

import ads_mcp.utils as utils

keyword_planner_mcp = FastMCP("keyword_planner")

_MAX_HISTORY_MONTHS = 48

_API_DEFAULT_HISTORY_MONTHS = 12

# MonthOfYear is offset (JANUARY = 2 ... DECEMBER = 13), so calendar month
# numbers must never be assigned to the enum directly.
_MONTH_NAMES = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)

_YearMonth = Tuple[int, int]


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


def _month_index(year: int, month: int) -> int:
    """Converts a (year, calendar month) pair into a monotonic month counter."""
    return year * 12 + (month - 1)


def _from_month_index(index: int) -> _YearMonth:
    """Inverse of `_month_index`."""
    return index // 12, index % 12 + 1


def _last_complete_month() -> _YearMonth:
    """Returns the most recent month that lies fully in the past.

    Search volume for the running month is still incomplete, so it is never a
    sensible end of a trend window.
    """
    today = datetime.date.today()
    return _from_month_index(_month_index(today.year, today.month) - 1)


def _parse_year_month(value: str, field: str) -> _YearMonth:
    """Parses a 'YYYY-MM' string into a (year, calendar month) pair."""
    parts = value.strip().split("-")
    is_numeric_pair = len(parts) == 2 and all(part.isdigit() for part in parts)
    if not is_numeric_pair:
        raise ToolError(
            f"{field} must be in 'YYYY-MM' format (e.g. '2022-09'), "
            f"got '{value}'."
        )

    year, month = int(parts[0]), int(parts[1])
    if not 1 <= month <= 12:
        raise ToolError(f"{field} has an invalid month: '{value}'.")
    return year, month


def _resolve_year_month_range(
    months_back: int | None,
    start_year_month: str | None,
    end_year_month: str | None,
) -> Tuple[_YearMonth, _YearMonth] | None:
    """Resolves the requested history window into inclusive start/end months.

    An explicit `start_year_month` or `end_year_month` wins over `months_back`.
    Returns None when nothing was requested, which leaves the request without a
    year_month_range so the API default of the past 12 months applies.
    """
    if months_back is not None and not 1 <= months_back <= _MAX_HISTORY_MONTHS:
        raise ToolError(
            f"months_back must be between 1 and {_MAX_HISTORY_MONTHS}; the API "
            "only serves search volume for the past 4 years."
        )

    has_explicit_bound = bool(start_year_month or end_year_month)
    if not has_explicit_bound and months_back is None:
        return None

    end = (
        _parse_year_month(end_year_month, "end_year_month")
        if end_year_month
        else _last_complete_month()
    )

    if start_year_month:
        start = _parse_year_month(start_year_month, "start_year_month")
    else:
        span = months_back or _API_DEFAULT_HISTORY_MONTHS
        start = _from_month_index(_month_index(*end) - (span - 1))

    if _month_index(*start) > _month_index(*end):
        raise ToolError(
            "start_year_month must not be after end_year_month "
            f"(got '{start[0]}-{start[1]:02d}' to '{end[0]}-{end[1]:02d}')."
        )
    return start, end


def _apply_year_month_range(
    request: Any,
    months_back: int | None,
    start_year_month: str | None,
    end_year_month: str | None,
) -> None:
    """Sets `historical_metrics_options.year_month_range` on a request."""
    window = _resolve_year_month_range(
        months_back, start_year_month, end_year_month
    )
    if window is None:
        return

    (start_year, start_month), (end_year, end_month) = window
    year_month_range = request.historical_metrics_options.year_month_range
    year_month_range.start.year = start_year
    year_month_range.start.month = _MONTH_NAMES[start_month - 1]
    year_month_range.end.year = end_year
    year_month_range.end.month = _MONTH_NAMES[end_month - 1]


def _normalize_monthly_volumes(metrics: Any) -> None:
    """Makes the monthly search volumes of a formatted metrics dict readable.

    `format_output_value` serializes enums as integers and MonthOfYear starts at
    JANUARY = 2, so a raw month of 4 actually means March. Each entry gets the
    month name plus a sortable 'YYYY-MM' `year_month` key for trend analysis.
    """
    if not isinstance(metrics, dict):
        return

    for volume in metrics.get("monthly_search_volumes") or []:
        month = volume.get("month")
        if not isinstance(month, int) or not 2 <= month <= 13:
            continue

        calendar_month = month - 1
        volume["month"] = _MONTH_NAMES[calendar_month - 1]
        year = volume.get("year")
        if year:
            volume["year_month"] = f"{int(year):04d}-{calendar_month:02d}"


def _format_result_with_metrics(result: Any, metrics_key: str) -> Any:
    """Formats one result and normalizes its monthly search volumes."""
    formatted = utils.format_output_value(result)
    if isinstance(formatted, dict):
        _normalize_monthly_volumes(formatted.get(metrics_key))
    return formatted


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
    months_back: int | None = None,
    start_year_month: str | None = None,
    end_year_month: str | None = None,
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

    ### history window
        Defaults to the API default of the past 12 months. For trend analysis
        request more via `months_back` (up to 48) or pin an exact window with
        `start_year_month`/`end_year_month`. Note that every extra month adds a
        `monthly_search_volumes` entry to *every* idea, so combine a long window
        with a `limit`. For a long history on a known keyword set, prefer
        `generate_keyword_historical_metrics`, which defaults to 48 months.

    Args:
        customer_id: The id of the customer.
        geo_target_constants: One or more geo targets to scope metrics to.
        language: The language to scope metrics to.
        keywords: Seed keywords to expand from.
        page_url: A seed landing page URL to derive ideas from.
        keyword_plan_network: Which network the metrics apply to.
        include_adult_keywords: Whether to include adult keywords in the results.
        limit: Maximum number of ideas to return (client-side cap).
        months_back: How many months of history to request, ending with the last
            complete month. Max 48. Omit for the API default of 12.
        start_year_month: Inclusive start of an exact window, as 'YYYY-MM'.
            Overrides `months_back`.
        end_year_month: Inclusive end of an exact window, as 'YYYY-MM'. Defaults
            to the last complete month.
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
    _apply_year_month_range(
        request, months_back, start_year_month, end_year_month
    )

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
        ideas.append(
            _format_result_with_metrics(result, "keyword_idea_metrics")
        )
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
    months_back: int | None = _MAX_HISTORY_MONTHS,
    start_year_month: str | None = None,
    end_year_month: str | None = None,
) -> List[Dict[str, Any]]:
    """Returns historical metrics (search volume, competition, CPC bid ranges) for specific keywords.

    Unlike `generate_keyword_ideas`, this does not expand seeds; it reports
    metrics for exactly the keywords you pass.

    See `generate_keyword_ideas` for the accepted `customer_id`,
    `geo_target_constants`, `language`, and `keyword_plan_network` formats.

    ### history window
        Defaults to the full 48 months the API offers, so `monthly_search_volumes`
        can be read as a multi-year demand trend including seasonality. Pass a
        smaller `months_back`, or pin an exact window with
        `start_year_month`/`end_year_month`, e.g. to compare like-for-like
        periods across years. The API caps search volume at 4 years and silently
        returns only the months it has, so an over-wide window is not an error.

    Args:
        customer_id: The id of the customer.
        keywords: The exact keywords to fetch metrics for.
        geo_target_constants: One or more geo targets to scope metrics to.
        language: The language to scope metrics to.
        keyword_plan_network: Which network the metrics apply to.
        include_adult_keywords: Whether to include adult keywords in the results.
        months_back: How many months of history to request, ending with the last
            complete month. Max 48.
        start_year_month: Inclusive start of an exact window, as 'YYYY-MM'.
            Overrides `months_back`.
        end_year_month: Inclusive end of an exact window, as 'YYYY-MM'. Defaults
            to the last complete month.
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
    _apply_year_month_range(
        request, months_back, start_year_month, end_year_month
    )

    response = service.generate_keyword_historical_metrics(request=request)
    return [
        _format_result_with_metrics(result, "keyword_metrics")
        for result in response.results
    ]


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
