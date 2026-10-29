"""Persistent, validated change proposals for a single local operator.

Design references and license notices are in docs/extensions.md.
No API that accepts arbitrary mutation payloads is exposed as an MCP tool.
"""

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from decimal import Decimal, InvalidOperation

from fastmcp.exceptions import ToolError
from google.ads.googleads.errors import GoogleAdsException
from google.api_core import exceptions as api_errors

from ads_mcp import utils


def identifier(value):
    text = str(value).strip().replace("-", "")
    if not re.fullmatch(r"[0-9]+", text) or int(text) == 0:
        raise ToolError("Expected a positive numeric identifier.")
    return text


def customer(value):
    text = identifier(value)
    if len(text) != 10:
        raise ToolError("Customer ID must contain exactly ten digits.")
    return text


def money(value):
    try:
        amount = Decimal(str(value))
        micros = amount * 1_000_000
        if not amount.is_finite() or amount <= 0:
            raise ValueError()
        if micros != micros.to_integral_value():
            raise ValueError()
        if micros > 9_223_372_036_854_775_807:
            raise ValueError()
        return int(micros)
    except (InvalidOperation, ValueError, OverflowError):
        raise ToolError("Use a positive finite amount with at most 6 decimals.")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    path = (
        Path(
            os.environ.get(
                "GOOGLE_ADS_MCP_PROPOSALS_DB",
                base / "google-ads-mcp/proposals.db",
            )
        )
        .expanduser()
        .resolve()
    )
    repo = Path(__file__).resolve().parents[2]
    if path == repo or repo in path.parents:
        raise ToolError("Proposal database must be outside the source tree.")
    return path


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else _path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, state TEXT NOT NULL, body TEXT NOT NULL,
                digest TEXT NOT NULL, result TEXT, created REAL NOT NULL)""")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, body):
        plan_id = str(uuid.uuid4())
        raw = canonical(body)
        with self.connect() as db:
            db.execute(
                "INSERT INTO proposals VALUES (?, ?, ?, ?, NULL, ?)",
                (
                    plan_id,
                    "PREPARED",
                    raw,
                    hashlib.sha256(raw.encode()).hexdigest(),
                    time.time(),
                ),
            )
        return self.get(plan_id)

    def get(self, plan_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT state, body, digest, result, created FROM proposals "
                "WHERE id=?",
                (plan_id,),
            ).fetchone()
        if not row:
            raise ToolError("Proposal not found.")
        if hashlib.sha256(row[1].encode()).hexdigest() != row[2]:
            raise ToolError("Proposal integrity check failed.")
        return dict(
            plan_id=plan_id,
            state=row[0],
            proposal=json.loads(row[1]),
            result=json.loads(row[3]) if row[3] else None,
            created=row[4],
        )

    def transition(self, plan_id, old, new, result=None):
        with self.connect() as db:
            count = db.execute(
                "UPDATE proposals SET state=?, result=? WHERE id=? AND state=?",
                (
                    new,
                    canonical(result) if result is not None else None,
                    plan_id,
                    old,
                ),
            ).rowcount
        if count != 1:
            raise ToolError("Proposal already claimed, cancelled or completed.")


def service(name, login=None):
    from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor

    return utils.get_googleads_client(login_customer_id=login).get_service(
        name, version="v25", interceptors=[MCPHeaderInterceptor()]
    )


def query(cid, resource, fields, where, login=None, limit=None):
    ga_service = service("GoogleAdsService", login)
    gaql = f"SELECT {', '.join(fields)} FROM {resource}"
    if where:
        gaql += f" WHERE {where}"
    if limit is not None:
        gaql += f" LIMIT {int(limit)}"
    rows = ga_service.search(
        customer_id=cid, query=gaql, retry=None, timeout=30
    )
    from google.ads.googleads.util import get_nested_attr

    result = [
        {
            field: utils.format_output_value(
                get_nested_attr(
                    row,
                    ".".join(
                        "type_" if part == "type" else part
                        for part in field.split(".")
                    ),
                )
            )
            for field in fields
        }
        for row in rows
    ]
    return sorted(result, key=canonical)


def watch(cid, resource, fields, where, login=None):
    return dict(
        resource=resource,
        fields=fields,
        where=where,
        before=query(cid, resource, fields, where, login),
    )


def reread(cid, item, login=None):
    return query(cid, item["resource"], item["fields"], item["where"], login)


def mutate(cid, operations, login, validate_only):
    ga_service = service("GoogleAdsService", login)
    return ga_service.mutate(
        request=dict(
            customer_id=cid,
            mutate_operations=operations,
            validate_only=validate_only,
            partial_failure=False,
        ),
        retry=None,
        timeout=30,
    )


def limits(cid, currency, operations):
    try:
        config = json.loads(
            os.environ.get("GOOGLE_ADS_MCP_ACCOUNT_LIMITS", "{}")
        )
        rule = config.get(cid)
        if not rule:
            return
        if rule["currency_code"] != currency:
            raise ToolError("Configured limit currency differs from account.")
        for item in operations:
            key, operation = next(iter(item.items()))
            value = operation.get("create", operation.get("update", {}))
            candidates = []
            if key == "campaign_budget_operation":
                candidates.append((value.get("amount_micros"), "daily_budget"))
            candidates.append((value.get("cpc_bid_micros"), "cpc_bid"))
            ceiling = value.get("target_spend", {}).get(
                "cpc_bid_ceiling_micros"
            )
            candidates.append((ceiling, "cpc_bid"))
            for amount, name in candidates:
                if amount is not None and name in rule:
                    if int(amount) > money(rule[name]):
                        raise ToolError(f"Configured {name} limit exceeded.")
    except (ValueError, KeyError, TypeError):
        raise ToolError("Invalid GOOGLE_ADS_MCP_ACCOUNT_LIMITS configuration.")


def prepare(cid, login, action, operations, watches, currency, checks):
    if not operations:
        raise ToolError("No changes supplied.")
    if len(operations) > 1000:
        raise ToolError(
            "Split this proposal into batches of at most 1000 operations."
        )
    limits(cid, currency, operations)
    mutate(cid, operations, login, True)
    # Validation is read-only; catch changes that happened during validation.
    for item in watches:
        if reread(cid, item, login) != item["before"]:
            raise ToolError(
                "Account changed during preparation; prepare again."
            )
    body = dict(
        customer_id=cid,
        login_customer_id=login,
        action=action,
        currency_code=currency,
        operations=operations,
        watches=watches,
        checks=checks,
        validation="GOOGLE_VALIDATED",
        approval="Show this exact proposal and obtain user approval "
        "in the client before calling apply.",
    )
    return Store().create(body)


def _equivalent(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _equivalent(actual[k], v)
            for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_equivalent(a, b) for a, b in zip(actual, expected))
        )
    return str(actual) == str(expected)


def verify(body, resource_names):
    observations = []
    temporary = {}
    for operation, rn in zip(body["operations"], resource_names):
        create = next(iter(operation.values())).get("create", {})
        if create.get("resource_name"):
            temporary[create["resource_name"]] = rn
    for check in body["checks"]:
        rn = check.get("resource_name")
        if rn is None:
            rn = resource_names[check["operation_index"]]
        resource = check["resource"]
        fields = [f"{resource}.resource_name"] + list(check["expected"])
        if check.get("removed"):
            if resource not in ("shared_criterion", "campaign_criterion"):
                fields.append(f"{resource}.status")
        rows = query(
            body["customer_id"],
            resource,
            list(dict.fromkeys(fields)),
            f"{resource}.resource_name = '{rn}'",
            body["login_customer_id"],
        )
        if check.get("removed"):
            ok = not rows or all(
                r.get(f"{resource}.status") == "REMOVED" for r in rows
            )
        else:
            expected = {
                k: temporary.get(v, v) if isinstance(v, str) else v
                for k, v in check["expected"].items()
            }
            ok = len(rows) == 1 and _equivalent(rows[0], expected)
        observations.append(dict(resource_name=rn, matches=ok, rows=rows))
    return dict(
        verified=all(o["matches"] for o in observations),
        observations=observations,
    )


def apply(plan_id, confirmed):
    if not confirmed:
        raise ToolError(
            "Obtain approval in the client, then set confirmed=true."
        )
    store = Store()
    plan = store.get(plan_id)
    body = plan["proposal"]
    store.transition(plan_id, "PREPARED", "CHECKING")
    try:
        if time.time() - plan["created"] > 1800:
            raise ToolError("Proposal expired; prepare a fresh proposal.")
        for item in body["watches"]:
            if (
                reread(body["customer_id"], item, body["login_customer_id"])
                != item["before"]
            ):
                raise ToolError("Account changed; prepare a fresh proposal.")
        limits(body["customer_id"], body["currency_code"], body["operations"])
        mutate(
            body["customer_id"],
            body["operations"],
            body["login_customer_id"],
            True,
        )
    except Exception:
        store.transition(plan_id, "CHECKING", "REJECTED")
        raise
    # Persist BEFORE network dispatch. Crashes here remain non-retryable.
    store.transition(plan_id, "CHECKING", "APPLYING")
    try:
        response = mutate(
            body["customer_id"],
            body["operations"],
            body["login_customer_id"],
            False,
        )
    except (
        GoogleAdsException,
        api_errors.InvalidArgument,
        api_errors.PermissionDenied,
        api_errors.Unauthenticated,
    ):
        store.transition(plan_id, "APPLYING", "FAILED")
        raise
    except Exception:
        store.transition(plan_id, "APPLYING", "UNKNOWN")
        raise ToolError(
            "Outcome uncertain. Inspect proposal and account; "
            "do not retry this mutation or recreate it blindly."
        )
    result = dict(verified=False)
    try:
        if response.partial_failure_error.code:
            raise ToolError("Unexpected partial failure; inspect the account.")
        names = []
        for result in response.mutate_operation_responses:
            field = result._pb.WhichOneof("response")
            names.append(getattr(result, field).resource_name if field else "")
        result = dict(resource_names=names)
        result.update(verify(body, names))
        state = "APPLIED" if result["verified"] else "UNVERIFIED"
    except Exception:
        state = "UNVERIFIED"
        result.update(
            verified=False,
            note="Mutation returned; verification "
            "failed. Inspect account before any further changes.",
        )
    store.transition(plan_id, "APPLYING", state, result)
    return store.get(plan_id)


def reconcile(plan_id):
    """Read-only recovery. Never resubmits a mutation or unlocks a proposal."""
    plan = Store().get(plan_id)
    result = plan.get("result") or {}
    names = result.get("resource_names", [])
    if (
        any(c.get("resource_name") is None for c in plan["proposal"]["checks"])
        and not names
    ):
        return dict(
            state=plan["state"],
            note="Creation outcome requires manual "
            "account inspection; no resource IDs were received.",
        )
    return dict(
        state=plan["state"],
        observations=verify(plan["proposal"], names),
        note="Read-only observation; proposal remains non-retryable.",
    )
