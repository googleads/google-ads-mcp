"""Purpose-built, read-only Google Ads reporting workflows."""

from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ads_mcp.tools.search import search

reporting_mcp = FastMCP("reporting")


def _date_conditions(start_date: str | None, end_date: str | None) -> list[str]:
    if bool(start_date) != bool(end_date):
        raise ValueError("start_date and end_date must be supplied together.")
    if not start_date:
        return ["segments.date DURING LAST_30_DAYS"]
    return [f"segments.date BETWEEN '{start_date}' AND '{end_date}'"]


def _run(
    customer_id: str | int,
    resource: str,
    fields: list[str],
    conditions: list[str],
    login_customer_id: str | int | None,
    account_name: str | None,
) -> list[dict[str, Any]]:
    return search(
        customer_id=customer_id,
        resource=resource,
        fields=fields,
        conditions=conditions,
        login_customer_id=login_customer_id,
        account_name=account_name,
    )


@reporting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def campaign_diagnostics(
    customer_id: str | int,
    start_date: str | None = None,
    end_date: str | None = None,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    """Returns campaign delivery, spend, click, and conversion diagnostics."""
    return _run(
        customer_id,
        "campaign",
        [
            "campaign.id",
            "campaign.name",
            "campaign.status",
            "campaign.bidding_strategy_type",
            "campaign_budget.amount_micros",
            "metrics.impressions",
            "metrics.clicks",
            "metrics.cost_micros",
            "metrics.conversions",
            "metrics.conversions_value",
        ],
        _date_conditions(start_date, end_date),
        login_customer_id,
        account_name,
    )


@reporting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_term_report(
    customer_id: str | int,
    start_date: str | None = None,
    end_date: str | None = None,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    """Returns search terms with their campaign, match type, and performance."""
    return _run(
        customer_id,
        "search_term_view",
        [
            "search_term_view.search_term",
            "segments.search_term_match_type",
            "campaign.id",
            "campaign.name",
            "metrics.impressions",
            "metrics.clicks",
            "metrics.cost_micros",
            "metrics.conversions",
        ],
        _date_conditions(start_date, end_date),
        login_customer_id,
        account_name,
    )


@reporting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def budget_report(
    customer_id: str | int,
    start_date: str | None = None,
    end_date: str | None = None,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    """Returns campaign budgets alongside spend and delivery metrics."""
    return _run(
        customer_id,
        "campaign",
        [
            "campaign.id",
            "campaign.name",
            "campaign.status",
            "campaign_budget.amount_micros",
            "campaign_budget.total_amount_micros",
            "metrics.cost_micros",
            "metrics.impressions",
            "metrics.clicks",
        ],
        _date_conditions(start_date, end_date),
        login_customer_id,
        account_name,
    )


@reporting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def conversion_report(
    customer_id: str | int,
    start_date: str | None = None,
    end_date: str | None = None,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    """Returns conversion volume, value, cost, and value-per-cost by campaign."""
    return _run(
        customer_id,
        "campaign",
        [
            "campaign.id",
            "campaign.name",
            "metrics.conversions",
            "metrics.conversions_value",
            "metrics.all_conversions",
            "metrics.cost_micros",
            "metrics.value_per_conversion",
            "metrics.value_per_all_conversions",
        ],
        _date_conditions(start_date, end_date),
        login_customer_id,
        account_name,
    )


@reporting_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def performance_anomalies(
    customer_id: str | int,
    threshold_percent: float = 30.0,
    login_customer_id: str | int | None = None,
    account_name: str | None = None,
) -> list[dict[str, Any]]:
    """Returns day-over-day campaign metric changes exceeding threshold_percent."""
    if threshold_percent <= 0:
        raise ValueError("threshold_percent must be positive.")
    rows = _run(
        customer_id,
        "campaign",
        [
            "segments.date",
            "campaign.id",
            "campaign.name",
            "campaign.status",
            "metrics.impressions",
            "metrics.clicks",
            "metrics.cost_micros",
            "metrics.conversions",
            "metrics.conversions_value",
        ],
        ["segments.date DURING LAST_30_DAYS"],
        login_customer_id,
        account_name,
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["campaign.id"]), []).append(row)

    anomalies: list[dict[str, Any]] = []
    metrics = ("metrics.clicks", "metrics.cost_micros", "metrics.conversions")
    for campaign_rows in grouped.values():
        campaign_rows.sort(key=lambda row: str(row["segments.date"]))
        for previous, current in zip(campaign_rows, campaign_rows[1:]):
            for metric in metrics:
                previous_value = float(previous.get(metric, 0) or 0)
                current_value = float(current.get(metric, 0) or 0)
                if previous_value == 0:
                    continue
                change_percent = (
                    (current_value - previous_value) / previous_value
                ) * 100
                if abs(change_percent) >= threshold_percent:
                    anomalies.append(
                        {
                            "campaign.id": current["campaign.id"],
                            "campaign.name": current["campaign.name"],
                            "date": current["segments.date"],
                            "metric": metric,
                            "previous_value": previous_value,
                            "current_value": current_value,
                            "change_percent": round(change_percent, 2),
                        }
                    )
    return anomalies
