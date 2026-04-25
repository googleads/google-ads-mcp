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

"""Audience tools — Customer Match user lists + ad-group / campaign targeting.

Customer Match workflow for "upload my paid users, target lookalikes":

  1. create_customer_match_user_list(name, upload_key_type='CONTACT_INFO')
  2. upload_customer_match_contacts(user_list_id, contacts=[...])
     (we normalize + SHA256-hash emails/phones for you)
  3. attach_user_list_to_ad_group(ad_group_id, user_list_id,
         targeting_mode='OBSERVATION')   # or 'TARGETING'

Observation mode lets Smart Bidding optimize for matched users without
restricting reach. Targeting mode restricts delivery to matched users only.
"""

import hashlib
import re
from typing import Any

from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.coordinator import mcp
from ads_mcp.tools import _common


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_NON_DIGIT = re.compile(r"[^\d+]")


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError(f"Invalid email: {email!r}")
    # Gmail ignores dots in the local-part, but Google's own docs say NOT to
    # strip dots for customer match; only strip whitespace and lowercase.
    return email


def _normalize_phone(phone: str) -> str:
    p = _PHONE_NON_DIGIT.sub("", phone.strip())
    if not p.startswith("+"):
        # Customer Match requires E.164; reject unparseable numbers loudly.
        raise ValueError(
            f"Phone {phone!r} is not in E.164 format. Pass '+14155551234', "
            "not '415-555-1234'."
        )
    return p


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_user_lists(
    customer_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Lists audiences / user lists in the account (includes Customer Match, remarketing)."""
    query = (
        "SELECT user_list.id, user_list.name, user_list.description, "
        "user_list.type, user_list.membership_status, "
        "user_list.membership_life_span, user_list.size_for_display, "
        "user_list.size_for_search, user_list.eligible_for_search, "
        "user_list.eligible_for_display, user_list.resource_name "
        f"FROM user_list LIMIT {int(limit)}"
    )
    return _common.gaql_search(customer_id, query)


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def create_customer_match_user_list(
    customer_id: str,
    name: str,
    description: str | None = None,
    membership_life_span_days: int = 540,
    upload_key_type: str = "CONTACT_INFO",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Creates a Customer Match user list (CRM-based).

    Args:
        name: Unique list name.
        description: Optional.
        membership_life_span_days: How long a contact stays in the list
            without re-upload. Max 540 (~18 months). Use 10000 for unlimited.
        upload_key_type: 'CONTACT_INFO' (email/phone/name+address),
            'CRM_ID' (your own ids), or 'MOBILE_ADVERTISING_ID' (IDFA/GAID).
        dry_run: If True, runs validate_only.
    """
    client = utils.get_googleads_client()
    service = client.get_service("UserListService")
    op = client.get_type("UserListOperation")
    u = op.create
    u.name = name
    if description:
        u.description = description
    u.membership_life_span = int(membership_life_span_days)
    u.crm_based_user_list.upload_key_type = (
        client.enums.CustomerMatchUploadKeyTypeEnum[upload_key_type]
    )
    u.membership_status = client.enums.UserListMembershipStatusEnum.OPEN

    with _common.google_ads_errors():
        response = service.mutate_user_lists(
            request=_common.build_request(
                client, "MutateUserListsRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def upload_customer_match_contacts(
    customer_id: str,
    user_list_id: str,
    contacts: list[dict[str, Any]],
    consent_ad_user_data: str = "GRANTED",
    consent_ad_personalization: str = "GRANTED",
) -> dict[str, Any]:
    """Uploads contacts to a Customer Match user list.

    The server normalizes and SHA256-hashes emails, phones, and name/address
    fields so you can pass plain strings. Contact dicts may include any of:

      - email (str)
      - phone (str, E.164, e.g. '+14155551234')
      - first_name + last_name + country_code + postal_code
      - mobile_id (IDFA/GAID — only for lists with upload_key_type='MOBILE_ADVERTISING_ID')
      - user_id (your own ID — only for lists with upload_key_type='CRM_ID')

    At least one identifier per contact. More identifiers per contact = higher
    match rate. Expect a 30–70% match rate on email-only lists.

    Consent: required under EU / 2026 global rules. 'GRANTED' / 'DENIED' /
    'UNSPECIFIED'. If unsure, set both to 'UNSPECIFIED' so Google's defaults
    apply — 'GRANTED' is only correct if you actually have explicit consent.

    This call creates + runs an OfflineUserDataJob synchronously and waits for
    the run to be queued. Actual matching takes 6-24 hours on Google's side.
    """
    client = utils.get_googleads_client()
    user_list_resource = f"customers/{customer_id}/userLists/{user_list_id}"
    job_service = client.get_service("OfflineUserDataJobService")

    # 1. Create the job
    job = client.get_type("OfflineUserDataJob")
    job.type_ = (
        client.enums.OfflineUserDataJobTypeEnum.CUSTOMER_MATCH_USER_LIST
    )
    job.customer_match_user_list_metadata.user_list = user_list_resource
    job.customer_match_user_list_metadata.consent.ad_user_data = (
        client.enums.ConsentStatusEnum[consent_ad_user_data]
    )
    job.customer_match_user_list_metadata.consent.ad_personalization = (
        client.enums.ConsentStatusEnum[consent_ad_personalization]
    )

    with _common.google_ads_errors():
        create_job_response = job_service.create_offline_user_data_job(
            customer_id=customer_id, job=job
        )
    job_resource = create_job_response.resource_name

    # 2. Build operations
    operations = []
    skipped = 0
    for c in contacts:
        op = client.get_type("OfflineUserDataJobOperation")
        data = op.create
        has_identifier = False

        if c.get("email"):
            email = _normalize_email(c["email"])
            ui = client.get_type("UserIdentifier")
            ui.hashed_email = _sha256_hex(email)
            data.user_identifiers.append(ui)
            has_identifier = True
        if c.get("phone"):
            phone = _normalize_phone(c["phone"])
            ui = client.get_type("UserIdentifier")
            ui.hashed_phone_number = _sha256_hex(phone)
            data.user_identifiers.append(ui)
            has_identifier = True
        if c.get("first_name") and c.get("last_name") and c.get(
            "country_code"
        ) and c.get("postal_code"):
            ui = client.get_type("UserIdentifier")
            ui.address_info.hashed_first_name = _sha256_hex(
                c["first_name"].strip().lower()
            )
            ui.address_info.hashed_last_name = _sha256_hex(
                c["last_name"].strip().lower()
            )
            ui.address_info.country_code = c["country_code"]
            ui.address_info.postal_code = c["postal_code"]
            data.user_identifiers.append(ui)
            has_identifier = True
        if c.get("mobile_id"):
            ui = client.get_type("UserIdentifier")
            ui.mobile_id = c["mobile_id"]
            data.user_identifiers.append(ui)
            has_identifier = True
        if c.get("user_id"):
            ui = client.get_type("UserIdentifier")
            ui.third_party_user_id = c["user_id"]
            data.user_identifiers.append(ui)
            has_identifier = True

        if not has_identifier:
            skipped += 1
            continue
        operations.append(op)

    if not operations:
        return {
            "error": "No valid contacts — every row must carry at least one "
            "of email, phone, name+address, mobile_id, or user_id.",
            "skipped": skipped,
        }

    # 3. Add operations (can be called multiple times for large uploads)
    with _common.google_ads_errors():
        add_response = job_service.add_offline_user_data_job_operations(
            request=_common.build_request(
                client, "AddOfflineUserDataJobOperationsRequest",
                resource_name=job_resource,
                operations=operations,
                enable_partial_failure=True,
            )
        )

    # 4. Kick the job
    with _common.google_ads_errors():
        job_service.run_offline_user_data_job(resource_name=job_resource)

    partial_failure = None
    if (
        add_response.partial_failure_error
        and add_response.partial_failure_error.message
    ):
        partial_failure = {
            "code": add_response.partial_failure_error.code,
            "message": add_response.partial_failure_error.message,
        }

    return {
        "job_resource_name": job_resource,
        "operations_sent": len(operations),
        "contacts_skipped_no_identifier": skipped,
        "partial_failure": partial_failure,
        "note": (
            "Matching takes 6-24h on Google's side. Poll with a search query: "
            "\"SELECT offline_user_data_job.status, offline_user_data_job.failure_reason "
            "FROM offline_user_data_job WHERE offline_user_data_job.resource_name = "
            f"'{job_resource}'\"."
        ),
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def attach_user_list_to_ad_group(
    customer_id: str,
    ad_group_id: str,
    user_list_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Attaches a user list to an ad group as an AdGroupCriterion.

    Whether the ad group actually *restricts* serving to matched users
    (TARGETING mode) versus just observing them (OBSERVATION mode) is not
    controlled here — it's governed by the ad group's
    `targeting_setting.target_restrictions`. This tool creates the criterion;
    by default the ad group's existing targeting setting is respected. For
    most paid-acquisition flows you want OBSERVATION, which lets Smart
    Bidding weight the audience without shrinking reach.
    """
    client = utils.get_googleads_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    c = op.create
    c.ad_group = _common.ad_group_path(customer_id, ad_group_id)
    c.user_list.user_list = (
        f"customers/{customer_id}/userLists/{user_list_id}"
    )
    c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
    with _common.google_ads_errors():
        response = service.mutate_ad_group_criteria(
            request=_common.build_request(
                client, "MutateAdGroupCriteriaRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }


@mcp.tool(
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False)
)
def attach_user_list_to_campaign(
    customer_id: str,
    campaign_id: str,
    user_list_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Attaches a user list to a campaign as a CampaignCriterion (observation only at campaign scope)."""
    client = utils.get_googleads_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    c = op.create
    c.campaign = _common.campaign_path(customer_id, campaign_id)
    c.user_list.user_list = (
        f"customers/{customer_id}/userLists/{user_list_id}"
    )
    with _common.google_ads_errors():
        response = service.mutate_campaign_criteria(
            request=_common.build_request(
                client, "MutateCampaignCriteriaRequest",
                customer_id=customer_id,
                operations=[op],
                validate_only=dry_run,
            )
        )
    return {
        "dry_run": dry_run,
        "results": [{"resource_name": r.resource_name} for r in response.results],
    }
