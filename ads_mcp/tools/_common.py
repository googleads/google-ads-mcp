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

"""Shared helpers for mutate-style tools.

Error handling strategy:
- All API calls are wrapped in `google_ads_errors()` which converts a
  `GoogleAdsException` into a `ToolError`. The message is structured so an LLM
  can read the error code, the field path that failed, and a short hint about
  how to recover. The hints cover the most common failures we'd expect when an
  AI is authoring campaigns: bad customer_id, missing OAuth, unknown resource,
  rate limits, policy rejections, etc.
"""

import json
from contextlib import contextmanager
from typing import Any, Iterable

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException

import ads_mcp.utils as utils


def customer_path(customer_id: str) -> str:
    return f"customers/{customer_id}"


def campaign_path(customer_id: str, campaign_id: str | int) -> str:
    return f"customers/{customer_id}/campaigns/{campaign_id}"


def campaign_budget_path(customer_id: str, budget_id: str | int) -> str:
    return f"customers/{customer_id}/campaignBudgets/{budget_id}"


def ad_group_path(customer_id: str, ad_group_id: str | int) -> str:
    return f"customers/{customer_id}/adGroups/{ad_group_id}"


def ad_group_ad_path(
    customer_id: str, ad_group_id: str | int, ad_id: str | int
) -> str:
    return f"customers/{customer_id}/adGroupAds/{ad_group_id}~{ad_id}"


def ad_group_criterion_path(
    customer_id: str, ad_group_id: str | int, criterion_id: str | int
) -> str:
    return (
        f"customers/{customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}"
    )


def campaign_criterion_path(
    customer_id: str, campaign_id: str | int, criterion_id: str | int
) -> str:
    return (
        f"customers/{customer_id}/campaignCriteria/{campaign_id}~{criterion_id}"
    )


def conversion_action_path(
    customer_id: str, conversion_action_id: str | int
) -> str:
    return (
        f"customers/{customer_id}/conversionActions/{conversion_action_id}"
    )


def ad_group_bid_modifier_path(
    customer_id: str, ad_group_id: str | int, criterion_id: str | int
) -> str:
    return (
        f"customers/{customer_id}/adGroupBidModifiers/{ad_group_id}~{criterion_id}"
    )


def geo_target_constant_path(geo_target_id: str | int) -> str:
    return f"geoTargetConstants/{geo_target_id}"


def language_constant_path(language_id: str | int) -> str:
    return f"languageConstants/{language_id}"


def micros(amount: float | int) -> int:
    """Convert a money amount (e.g. 12.34 USD) to micros (12340000)."""
    return int(round(float(amount) * 1_000_000))


@contextmanager
def google_ads_errors():
    """Translate GoogleAdsException into ToolError with request_id and details."""
    try:
        yield
    except GoogleAdsException as ex:
        errors = [_format_ads_error(e) for e in ex.failure.errors]
        raise ToolError(
            json.dumps(
                {
                    "error": "GoogleAdsApiError",
                    "request_id": ex.request_id,
                    "errors": errors,
                    "hint": _combined_hint(errors),
                    "remediation": (
                        "If this is a data/shape issue, retry with dry_run=True "
                        "to validate without side effects, then fix and retry."
                    ),
                },
                indent=2,
            )
        ) from ex


# Common error-code hints keyed by the last segment of the one-of field name
# (e.g. "authentication_error", "authorization_error", "quota_error") plus the
# enum value name (e.g. "CUSTOMER_NOT_ENABLED"). The LLM gets a short, actionable
# remediation string it can include in its reply to the user.
_ERROR_HINTS: dict[str, str] = {
    "authentication_error": (
        "OAuth token is missing or expired. In Claude, re-run `/mcp auth "
        "google-ads-mcp`. Check GOOGLE_ADS_DEVELOPER_TOKEN on the server."
    ),
    "authorization_error": (
        "The signed-in user does not have permission on this customer_id via "
        "MCC {GOOGLE_ADS_LOGIN_CUSTOMER_ID}. Pick a customer_id returned by "
        "list_accessible_customers."
    ),
    "quota_error": (
        "Rate-limited by the Google Ads API. Back off ~60s and retry, or "
        "batch fewer operations per call."
    ),
    "internal_error": (
        "Transient server error. Retry with exponential backoff (2s, 4s, 8s)."
    ),
    "request_error": (
        "The request shape is invalid. Check the `location` path; the field "
        "at that path has the wrong value or is missing."
    ),
    "resource_exhausted": (
        "Daily/monthly API quota hit. Retry tomorrow or request a quota bump."
    ),
    "not_whitelisted_for_calling_api": (
        "Your developer token lacks the required access level. Upgrade to "
        "Basic/Standard access in the Google Ads UI."
    ),
    "CUSTOMER_NOT_ENABLED": (
        "This customer account is closed or not yet enabled. The account owner "
        "needs to activate it in ads.google.com."
    ),
    "INVALID_CUSTOMER_ID": (
        "customer_id must be 10 digits with no hyphens. If you see "
        "123-456-7890, pass '1234567890'."
    ),
    "MISSING_LOGIN_CUSTOMER_ID": (
        "This call requires login_customer_id (the MCC id). Set "
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID on the server."
    ),
    "NOT_FOUND": (
        "Resource not found. Verify the id exists under this customer_id by "
        "calling the matching `list_*` or `get_*` tool first."
    ),
    "DUPLICATE_NAME": (
        "An entity with this name already exists. Pick a unique name or reuse "
        "the existing one."
    ),
    "BUDGET_AMOUNT_TOO_SMALL": (
        "Daily budget is below the account currency's minimum. Raise it."
    ),
    "POLICY_VIOLATION": (
        "Google's ad policy flagged the creative. Rephrase headlines/descriptions "
        "or remove the offending claim, then retry."
    ),
    "TOO_MANY_HEADLINES": "Responsive Search Ads accept at most 15 headlines.",
    "TOO_MANY_DESCRIPTIONS": "Responsive Search Ads accept at most 4 descriptions.",
    "AD_CUSTOMIZERS_NOT_SUPPORTED_FOR_AD_TYPE": (
        "Remove ad customizer tags like {KeyWord:...} from the asset text."
    ),
    "CRITERION_INVALID_EMAIL": (
        "Customer Match emails must be lowercased + trimmed; the server hashes "
        "them for you, so pass plain addresses."
    ),
}


def _format_ads_error(error) -> dict[str, Any]:
    """Extract structured info from a GoogleAdsError."""
    # error.error_code is a oneof; find the populated sub-field.
    code_group: str | None = None
    code_value: str | None = None
    for field in error.error_code._pb.DESCRIPTOR.fields:
        if error.error_code._pb.HasField(field.name):
            code_group = field.name
            value = getattr(error.error_code, field.name)
            code_value = value.name if hasattr(value, "name") else str(value)
            break

    location_parts: list[str] = []
    try:
        for el in error.location.field_path_elements:
            seg = el.field_name
            if el._pb.HasField("index"):
                seg += f"[{el.index}]"
            location_parts.append(seg)
    except (AttributeError, ValueError):
        pass

    trigger = None
    try:
        if error.trigger and error.trigger.string_value:
            trigger = error.trigger.string_value
    except AttributeError:
        pass

    hint = _ERROR_HINTS.get(code_value or "")
    if hint is None and code_group:
        hint = _ERROR_HINTS.get(code_group)

    return {
        "code": f"{code_group}.{code_value}" if code_group else "UNKNOWN",
        "message": error.message,
        "location": ".".join(location_parts) if location_parts else None,
        "trigger": trigger,
        "hint": hint,
    }


def _combined_hint(errors: list[dict[str, Any]]) -> str | None:
    """Pick the most specific hint across all errors."""
    hints = [e["hint"] for e in errors if e.get("hint")]
    return hints[0] if hints else None


def set_field_mask(operation, *paths: str) -> None:
    """Append paths to operation.update_mask.paths, deduplicated."""
    existing = set(operation.update_mask.paths)
    for p in paths:
        if p not in existing:
            operation.update_mask.paths.append(p)
            existing.add(p)


def _make_json_safe(value: Any) -> Any:
    """Coerce a value tree into something fastmcp + the MCP structured-output
    JSON validator will always accept.

    Why this is needed: `proto.Message.to_dict()` (used inside utils.format_output_value)
    can produce dicts containing bytes values, or — for nested resources like
    change_event.new_resource — values from proto well-known types that don't
    JSON-serialize cleanly. When fastmcp can't serialize the return value to
    structured content, it raises 'outputSchema defined but no structured
    output returned'. This function defangs the tree before the response
    leaves the tool.
    """
    import base64

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, dict):
        return {str(k): _make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_safe(v) for v in value]
    # Fall back to repr for anything exotic (Decimal, datetime, custom objects)
    # so the LLM still gets a readable value instead of a serializer crash.
    return repr(value)


def gaql_search(customer_id: str, query: str) -> list[dict]:
    """Run a GAQL query and return rows formatted via utils.format_output_row.

    Output is post-processed through `_make_json_safe` so that complex resource
    types (e.g. change_event.new_resource, change_event.changed_fields) don't
    trigger fastmcp's 'outputSchema defined but no structured output returned'
    validator with non-JSON-safe leaf values.
    """
    ga_service = utils.get_googleads_service("GoogleAdsService")
    with google_ads_errors():
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        out: list[dict] = []
        for batch in stream:
            for row in batch.results:
                out.append(
                    _make_json_safe(
                        utils.format_output_row(row, batch.field_mask.paths)
                    )
                )
        return out


def mutate_summary(response, op_kind: str) -> list[dict]:
    """Summarize a mutate response into a list of {resource_name} (or status)."""
    results = []
    for r in response.results:
        results.append({"resource_name": r.resource_name})
    return [{"operation": op_kind, "results": results}]


def build_request(client, request_type_name: str, **fields):
    """Construct any google-ads Request proto, setting fields universally.

    Why this exists: for every Mutate*/Upload*/Add* service in google-ads
    Python, fields like `validate_only`, `partial_failure`, and
    `enable_partial_failure` are NOT exposed as flat kwargs on the service
    method — they only live on the Request proto. Calling
    `service.mutate_x(customer_id=..., operations=..., validate_only=True)`
    raises `unexpected keyword argument 'validate_only'`. The fix is to
    construct the Request proto and pass it via `request=`. This helper
    builds that request from kwargs:

      req = build_request(
          client, "MutateCampaignBudgetsRequest",
          customer_id=customer_id,
          operations=[op],
          validate_only=dry_run,
      )
      service.mutate_campaign_budgets(request=req)

    Repeated fields (like `operations`) are .extend()ed; scalars are set.
    None values are skipped so callers can pass optionals freely.
    """
    request = client.get_type(request_type_name)
    for key, value in fields.items():
        if value is None:
            continue
        attr = getattr(request, key)
        if isinstance(value, (list, tuple)) and hasattr(attr, "extend"):
            attr.extend(value)
        else:
            setattr(request, key, value)
    return request


def comma_join(items: Iterable[str]) -> str:
    return ", ".join(f"'{i}'" for i in items)
