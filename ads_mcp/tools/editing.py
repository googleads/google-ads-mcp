"""Optional, separately namespaced Search editing tools."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ads_mcp.extensions import changes, search

editing_mcp = FastMCP("editing")
READ = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False
)


@editing_mcp.tool(annotations=READ)
def prepare_campaign(
    customer_id: str,
    change: search.Campaign,
    login_customer_id: str | None = None,
) -> dict:
    """Prepare and Google-validate a Search campaign change; never apply it.

    Creation requires explicit bidding and EU political advertising declaration.
    Show the complete proposal to the user before requesting apply.
    """
    return search.prepare(
        customer_id, login_customer_id, change, search.campaign
    )


@editing_mcp.tool(annotations=READ)
def prepare_budget(
    customer_id: str,
    change: search.Budget,
    login_customer_id: str | None = None,
) -> dict:
    """Prepare a budget change, showing all campaigns using a shared budget."""
    return search.prepare(customer_id, login_customer_id, change, search.budget)


@editing_mcp.tool(annotations=READ)
def prepare_ad_group(
    customer_id: str,
    change: search.AdGroup,
    login_customer_id: str | None = None,
) -> dict:
    """Prepare ad group creation, name, manual CPC or status changes."""
    return search.prepare(
        customer_id, login_customer_id, change, search.ad_group
    )


@editing_mcp.tool(annotations=READ)
def prepare_ad(
    customer_id: str, change: search.Ad, login_customer_id: str | None = None
) -> dict:
    """Prepare responsive Search ad creation, copy/URL edits or status changes."""
    return search.prepare(customer_id, login_customer_id, change, search.ad)


@editing_mcp.tool(annotations=READ)
def prepare_keywords(
    customer_id: str,
    change: search.Keywords,
    login_customer_id: str | None = None,
) -> dict:
    """Prepare positive keywords, manual bids/status or campaign/group negatives."""
    return search.prepare(
        customer_id, login_customer_id, change, search.keywords
    )


@editing_mcp.tool(annotations=READ)
def prepare_negative_list(
    customer_id: str,
    change: search.NegativeList,
    login_customer_id: str | None = None,
) -> dict:
    """Prepare shared negative list edits and campaign attachments atomically."""
    return search.prepare(
        customer_id, login_customer_id, change, search.negative_list
    )


@editing_mcp.tool(annotations=READ)
def list_negative_lists(
    customer_id: str, login_customer_id: str | None = None
) -> list[dict]:
    """List shared negative keyword lists; no mutation or proposal is created."""
    cid = changes.customer(customer_id)
    login = changes.customer(login_customer_id) if login_customer_id else None
    return changes.query(
        cid,
        "shared_set",
        ["shared_set.id", "shared_set.name", "shared_set.status"],
        "shared_set.type = 'NEGATIVE_KEYWORDS'",
        login,
    )


@editing_mcp.tool(annotations=READ)
def get_negative_list(
    customer_id: str, list_id: str, login_customer_id: str | None = None
) -> dict:
    """Read a negative list, its keyword criterion IDs and campaign links."""
    b = search.Build(customer_id, login_customer_id)
    rn, row = b.entity("shared_set", list_id)
    return dict(
        list=row,
        keywords=b.track(
            "shared_criterion", f"shared_criterion.shared_set = '{rn}'"
        ),
        campaigns=b.track(
            "campaign_shared_set", f"campaign_shared_set.shared_set = '{rn}'"
        ),
    )


@editing_mcp.tool(annotations=READ)
def get_proposal(plan_id: str) -> dict:
    """Read the exact saved proposal, validation, before values and result."""
    return changes.Store().get(plan_id)


@editing_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False
    )
)
def cancel_proposal(plan_id: str) -> dict:
    """Cancel a prepared local proposal; never change Google Ads."""
    store = changes.Store()
    store.transition(plan_id, "PREPARED", "CANCELLED")
    return store.get(plan_id)


@editing_mcp.tool(annotations=WRITE)
def apply_proposal(plan_id: str, confirmed: bool = False) -> dict:
    """Apply ONLY after the user approves the exact displayed proposal.

    Client is responsible for human approval. Never auto-confirm, apply an
    undisplayed proposal or retry an UNKNOWN/APPLYING/UNVERIFIED outcome.
    """
    return changes.apply(plan_id, confirmed)


@editing_mcp.tool(annotations=READ)
def reconcile_proposal(plan_id: str) -> dict:
    """Inspect uncertain results read-only; never retry or unlock a proposal."""
    return changes.reconcile(plan_id)
