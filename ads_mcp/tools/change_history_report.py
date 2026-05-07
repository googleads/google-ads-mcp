"""Change history report — who changed what and when."""

from typing import Any, Dict, List, Optional
from ads_mcp.coordinator import mcp
from mcp.types import ToolAnnotations
import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException
from fastmcp.exceptions import ToolError


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_change_history_report(
    customer_id: str,
    start_date: str,
    end_date: str,
    resource_type: Optional[str] = None,
    campaign_id: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Returns a log of changes made to the account — bids, budgets, statuses, ad copy, etc.

    Each row is one change event. Useful for correlating performance shifts with
    account modifications and for auditing who changed what.

    Note: Google Ads limits change_event queries to a maximum of 10000 rows and
    a lookback window of 30 days. start_date must be within the last 30 days.

    Args:
        customer_id: Client account ID, digits only (e.g. "1635583349").
        start_date: Start date in YYYY-MM-DD format. Must be within the last 30 days.
        end_date: End date in YYYY-MM-DD format.
        resource_type: Optional. Filter by resource type. Common values:
            CAMPAIGN, AD_GROUP, AD, AD_GROUP_CRITERION, CAMPAIGN_BUDGET,
            CAMPAIGN_CRITERION, FEED, FEED_ITEM, BIDDING_STRATEGY.
        campaign_id: Optional. Filter to changes within a single campaign.
        limit: Maximum rows to return (max 10000, default 1000).

    Returns:
        List of rows with:
        - change_date_time: timestamp of the change (RFC 3339)
        - resource_type: what type of resource was changed
        - operation: ADD, UPDATE, or REMOVE
        - changed_fields: dot-notation list of fields that were modified
        - user_email: who made the change (empty for automated changes)
        - client_type: GOOGLE_ADS_WEB_CLIENT, API, GOOGLE_ADS_AUTOMATED_RULE, etc.
        - campaign_id, ad_group_id (where applicable)
    """
    if limit > 10000:
        limit = 10000

    fields = [
        "change_event.change_date_time",
        "change_event.change_resource_type",
        "change_event.resource_change_operation",
        "change_event.changed_fields",
        "change_event.user_email",
        "change_event.client_type",
        "change_event.campaign",
        "change_event.ad_group",
    ]

    conditions = [
        f"change_event.change_date_time >= '{start_date} 00:00:00'",
        f"change_event.change_date_time <= '{end_date} 23:59:59'",
    ]
    if resource_type:
        conditions.append(f"change_event.change_resource_type = '{resource_type}'")
    if campaign_id:
        conditions.append(f"change_event.campaign = 'customers/{customer_id}/campaigns/{campaign_id}'")

    query = (
        f"SELECT {', '.join(fields)}"
        f" FROM change_event"
        f" WHERE {' AND '.join(conditions)}"
        f" ORDER BY change_event.change_date_time DESC"
        f" LIMIT {limit}"
        f" PARAMETERS omit_unselected_resource_names=true"
    )

    utils.logger.info(f"get_change_history_report query: {query}")
    ga_service = utils.get_googleads_service("GoogleAdsService")

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in response:
            for row in batch.results:
                ev = row.change_event
                rows.append({
                    "change_date_time": ev.change_date_time,
                    "resource_type": ev.change_resource_type.name,
                    "operation": ev.resource_change_operation.name,
                    "changed_fields": list(ev.changed_fields.paths),
                    "user_email": ev.user_email,
                    "client_type": ev.client_type.name,
                    "campaign_resource": str(ev.campaign),
                    "ad_group_resource": str(ev.ad_group),
                })
        return rows
    except GoogleAdsException as ex:
        error_msgs = [e.message for e in ex.failure.errors]
        raise ToolError(f"Request ID: {ex.request_id}\n" + "\n".join(error_msgs))
