# Search editing extensions

This fork keeps upstream Python/FastMCP and the original read tools unchanged.
Editing is opt-in: set `GOOGLE_ADS_MCP_TOOLS_CONFIG` to the absolute path of
`editing-tools.yaml`. The bundled default remains read-only, preserving the
upstream tool catalog and smoke contracts.

## Local deployment and approval

This version supports one trusted local operator using stdio. Do not expose
its SQLite proposal tools as a shared/multi-user endpoint: they are not a
tenant isolation or server-enforced human approval system. OAuth access to
Google is inherited from upstream. No new Google Cloud project is required.

Install independently with Python 3.10+ and
`pip install -c constraints-local.txt .`. Configure the client to execute this
installation's `google-ads-mcp-editing` entry point and retain its existing
Google credential environment. This local-only entry point selects the bundled
editing profile automatically; the standard `google-ads-mcp` stays read-only.
Restart the client connection and confirm that `editing_*` tools appear.
Keep the previous executable path for software rollback; rollback does not undo
Google Ads changes. Never put credentials, tokens or the proposal DB in Git.

On Windows, `scripts/activate-local.ps1 -ExecutablePath PATH` changes only the
existing Codex `google_ads.command` and saves a timestamped configuration backup.
Run it only after validation. It neither copies credentials into the repository
nor resets other MCP connections. A connection already running must be restarted
by the client to load the new executable.

All `editing_prepare_*` tools accept typed `change` inputs with an explicit
`action`. Unknown or action-inapplicable fields are rejected. Monetary inputs
are decimal strings in account currency (not dollars and not floats).
Supported actions are documented by each model's JSON schema:

| Tool | Actions |
| --- | --- |
| prepare_campaign | create, update, status, add_targeting, remove_targeting |
| prepare_budget | create, update |
| prepare_ad_group | create, update, status |
| prepare_ad | create, update, status |
| prepare_keywords | add, update, status, add_negatives, remove_negatives |
| prepare_negative_list | create, rename, add, remove_terms, attach, detach, remove |

Use `list_negative_lists` and `get_negative_list` for list/member/link IDs.
The unchanged `search_search` and metadata tools provide all other discovery.

### Example

Call `editing_prepare_campaign` with:

```json
{
  "customer_id": "1234567890",
  "change": {
    "action": "create",
    "name": "Search example",
    "daily_budget": "25000.00",
    "bidding": "MAXIMIZE_CLICKS",
    "max_cpc": "1500.00",
    "contains_eu_political_advertising": false
  }
}
```

Supply the actual political advertising declaration; never infer it. Creation
requires either an existing budget ID or a daily budget, not both. The campaign
and a new budget are validated/applied in the same atomic API request. All new
campaigns, ad groups, ads and positive keywords are PAUSED.

Show the saved proposal, account, currency, before values, operations and
affected campaign list to the user. After explicit chat approval, call
`editing_apply_proposal` with its `plan_id` and `confirmed: true`.
The client is responsible for obtaining human approval; a model-supplied
boolean is not independent evidence of approval.

## Persistence and failure semantics

Default DB: `%LOCALAPPDATA%/google-ads-mcp/proposals.db` on Windows,
`~/.local/share/google-ads-mcp/proposals.db` elsewhere. Override using
`GOOGLE_ADS_MCP_PROPOSALS_DB` (outside the source tree). It contains account
snapshots, exact operations, proposal state and outcomes, not credentials.
Protect it with the operator's normal filesystem permissions. No network
mutation occurs during prepare, get, cancel or reconcile; prepare does call
the API with `validate_only=true`. This does not guarantee ad policy approval.

Proposals expire after 30 minutes. Snapshot comparison and validation run again
before dispatch. SQLite compare-and-set permits a single claimant. A crash in
CHECKING or APPLYING is deliberately not unlocked automatically. Google does
not provide an atomic compare-and-swap over our snapshots; an external edit
between final check and mutation remains possible.

States: PREPARED, CANCELLED, CHECKING, REJECTED, APPLYING, FAILED, UNKNOWN,
UNVERIFIED, APPLIED. APPLIED means post-read checks matched, not ad delivery or
editorial approval. UNKNOWN/APPLYING and UNVERIFIED must never trigger automatic
resubmission. Use `reconcile_proposal` read-only and inspect the account. For
creation without returned IDs, manual reconciliation is required. Exceptions
from Google are surfaced as tool errors; no raw credentials are logged.

Per-account optional limits (no implicit common cap across currencies):

```text
GOOGLE_ADS_MCP_ACCOUNT_LIMITS={"1234567890":{"currency_code":"COP","daily_budget":"100000","cpc_bid":"5000"}}
```

Changing a budget lists all campaigns currently using it. Budgets affecting
non-Search campaigns are rejected. Negative list removals require detachment
first. Targeting removal only accepts location/language criteria. Negative
keyword removal is a separate explicit action. CPC changes require MANUAL_CPC.
One proposal targets one account; atomic mutation uses partial_failure=false,
at most 1000 operations, and no automatic retry on a write request.

## Verification and maintaining upstream compatibility

Run `python -m unittest discover -s tests -p '*_test.py'` and `nox -s lint`.
Also run `python -m unittest tests.smoke.smoke_test`. The read schemas explicitly
retain their original parameter descriptions across FastMCP updates; the search
golden description now reflects the existing extended discovery hints. The API
client is explicitly v25 to match upstream imports instead of silently selecting
an SDK-default v26 endpoint that returned Method not found in live verification.
Tests use real Google Ads protobuf types and mocked network responses; they
never mutate a real account. `scripts/verify_editing.py` provides opt-in real
reads and validate_only checks using an existing Codex configuration.

Develop on `codex/` branches and submit reviewable PRs to this fork. For
upstream updates, merge upstream/main into an integration branch, resolve code
conflicts, run upstream tests plus editing tests, then replace the installation.
Never synchronize using an option that discards fork commits. Upstream is
currently read-only: Python compatibility does not guarantee acceptance of
editing functionality. Send independent improvements as separate upstream PRs
and follow its CONTRIBUTING.md/CLA requirements.

## Provenance

Implementation is written in Python for this fork. No donor runtime or entire
fork was imported. The following pinned sources informed the adaptation:

- Official `googleads/google-ads-mcp`, base
  `9a78cbdceebae71a6bc8483bdec333695834ef9c` (Apache-2.0).
- `MarventoCapital/marvento-ads-mcp`,
  `6b112ac28196b1002b71bf361fb55b2cb94b6eb7` (Apache-2.0): Search operations,
  atomic validation, account-currency amounts. Enabled-child defaults and
  float rounding were replaced, not preserved.
- `Heyneuron/google-ads-mcp-extended`,
  `a5ace5beac8df52a41b1551a35b1d781bff2df1e` (Apache-2.0): input validation,
  configurable guards and outcome recording. Local-only previews are replaced
  with actual Google validation.
- `FGRibreau/mcp-google-ads`,
  `5e8d073b76bc723cfdb1978a345add69f3412a73` (MIT): draft/apply workflow,
  shared-set/criterion/campaign-link operations and temporary resource names,
  reimplemented in Python. No Rust source copied.

Upstream copyright notices and LICENSE remain intact.
