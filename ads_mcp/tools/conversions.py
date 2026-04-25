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

"""Conversion-action discovery + offline conversion upload."""

from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_conversion_actions(
    customer_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Lists ConversionActions in the account."""
    query = (
        "SELECT conversion_action.id, conversion_action.name, "
        "conversion_action.status, conversion_action.type, "
        "conversion_action.category, conversion_action.value_settings.default_value, "
        "conversion_action.value_settings.default_currency_code, "
        "conversion_action.click_through_lookback_window_days, "
        "conversion_action.resource_name "
        f"FROM conversion_action LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def upload_click_conversions(
    customer_id: str,
    conversions: list[dict[str, Any]],
    partial_failure: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Uploads offline click conversions (gclid-based).

    Use this to feed your real "paid user" signal back to Google Ads so Smart Bidding
    can optimize toward it.

    Args:
        customer_id: 10-digit customer id.
        conversions: list of dicts with keys:
          - conversion_action_id (str|int) — required, the ConversionAction id
          - gclid (str) — required, the click identifier captured at landing
          - conversion_date_time (str) — required, 'YYYY-MM-DD HH:MM:SS+TZ' (e.g. '2026-04-23 12:34:56+05:30')
          - conversion_value (float) — optional, value of the conversion
          - currency_code (str) — optional ISO 4217 (e.g. 'USD')
          - order_id (str) — optional, dedup key (recommended)
        partial_failure: If True, valid rows still upload when some rows fail.
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("ConversionUploadService")

    rows = []
    for c in conversions:
        cc = client.get_type("ClickConversion")
        cc.conversion_action = _common.conversion_action_path(
            customer_id, c["conversion_action_id"]
        )
        cc.gclid = c["gclid"]
        cc.conversion_date_time = c["conversion_date_time"]
        if "conversion_value" in c and c["conversion_value"] is not None:
            cc.conversion_value = float(c["conversion_value"])
        if "currency_code" in c and c["currency_code"]:
            cc.currency_code = c["currency_code"]
        if "order_id" in c and c["order_id"]:
            cc.order_id = c["order_id"]
        rows.append(cc)

    with _common.google_ads_errors():
        response = service.upload_click_conversions(
            request=_common.build_request(
                client, "UploadClickConversionsRequest",
                customer_id=customer_id,
                conversions=rows,
                partial_failure=partial_failure,
                validate_only=dry_run,
            )
        )

    out_rows = []
    for r in response.results:
        out_rows.append(
            {
                "gclid": r.gclid,
                "conversion_action": r.conversion_action,
                "conversion_date_time": r.conversion_date_time,
            }
        )
    partial_failure_error = None
    if response.partial_failure_error and response.partial_failure_error.message:
        partial_failure_error = {
            "code": response.partial_failure_error.code,
            "message": response.partial_failure_error.message,
        }
    return {
        "dry_run": dry_run,
        "results": out_rows,
        "partial_failure_error": partial_failure_error,
    }
