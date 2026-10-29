"""Opt-in live reads and validate_only; never calls apply or a real mutation.

Usage (Python 3.11+): python -m scripts.verify_editing --codex-config PATH
May select a readable client beneath a directly accessible manager. Prints
only validation status, not credentials or account names. No proposal applied.
"""

import argparse
import os
from pathlib import Path


def main():
    import tomllib

    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-config", required=True)
    args = parser.parse_args()
    config = tomllib.loads(Path(args.codex_config).read_text(encoding="utf-8"))
    env = config["mcp_servers"]["google_ads"].get("env", {})
    for key, value in env.items():
        os.environ[key] = str(value)
    from ads_mcp.extensions import changes as ch, search as s
    from google.ads.googleads.errors import GoogleAdsException

    accessible = (
        ch.service("CustomerService")
        .list_accessible_customers(retry=None, timeout=30)
        .resource_names
    )
    candidates = []
    for rn in accessible:
        cid = rn.rsplit("/", 1)[1]
        try:
            rows = ch.query(
                cid, "customer", ["customer.manager"], f"customer.id = {cid}"
            )
        except GoogleAdsException as exc:
            if any(
                e.error_code.authorization_error.name == "CUSTOMER_NOT_ENABLED"
                for e in exc.failure.errors
            ):
                continue
            raise
        if rows[0]["customer.manager"]:
            children = ch.query(
                cid,
                "customer_client",
                ["customer_client.id"],
                "customer_client.manager = FALSE AND customer_client.level <= 1",
                cid,
            )
            candidates.extend(
                (str(r["customer_client.id"]), cid) for r in children
            )
        else:
            candidates.append((cid, None))
    for cid, login in candidates:
        try:
            rows = ch.query(
                cid,
                "campaign",
                ["campaign.campaign_budget"],
                "campaign.advertising_channel_type = 'SEARCH' AND campaign.status != 'REMOVED'",
                login,
            )
        except GoogleAdsException as exc:
            if any(
                e.error_code.authorization_error.name == "CUSTOMER_NOT_ENABLED"
                for e in exc.failure.errors
            ):
                continue
            raise
        if not rows:
            continue
        budget_id = rows[0]["campaign.campaign_budget"].rsplit("/", 1)[1]
        b = s.Build(cid, login)
        # Exercise every snapshot field against the API, even for empty tables.
        for resource, names in s.FIELDS.items():
            ch.query(
                cid,
                resource,
                [f"{resource}.resource_name"]
                + [f"{resource}.{f}" for f in names],
                "",
                login,
                limit=1,
            )
        _, budget = b.entity("campaign_budget", budget_id)
        from decimal import Decimal

        amount = str(
            Decimal(str(budget["campaign_budget.amount_micros"])) / 1_000_000
        )
        s.budget(
            b,
            s.Budget(action="update", budget_id=budget_id, daily_amount=amount),
        )
        plan = b.finish("read-only live validation of unchanged budget")
        ch.Store().transition(plan["plan_id"], "PREPARED", "CANCELLED")
        print(
            "LIVE_READ_AND_VALIDATE_ONLY_OK; proposal cancelled; no account changed"
        )
        return
    raise RuntimeError("No accessible Search budget found for validation.")


if __name__ == "__main__":
    main()
