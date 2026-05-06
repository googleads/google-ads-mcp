# MCP Change Plan for Required Google Ads Reporting

This document explains, step by step, what changes would be needed if you want this MCP server to support only the Google Ads reporting use cases you listed while limiting generic campaign and ad-group reporting that you already have elsewhere.

No code changes are made by this document. This is a planning and implementation guide only.

## Goal

You want the MCP server to support these reporting categories:

- Impression Share
- Lost IS (Budget)
- Lost IS (Rank)
- Quality Score
- Ad Rank
- Keyword-level efficiency
- Search Term Report for negative keyword discovery
- Top-of-page rate
- Absolute top-of-page rate
- Audience analysis
- Change history
- Reach & Frequency
- Reach / frequency union and overlap math
- Auction Insights
- Keywords
- Product catalog
- TAM / audience size

You also want to avoid exposing broad generic reporting such as campaign or ad-group daily/hourly insights because that already exists in your current system.

## Current State of This MCP Server

The current MCP server is generic and thin. It mainly exposes:

- `search`
- `get_resource_metadata`
- `list_accessible_customers`

Relevant files:

- `ads_mcp/tools/search.py`
- `ads_mcp/tools/get_resource_metadata.py`
- `ads_mcp/tools/core.py`
- `ads_mcp/server.py`
- `ads_mcp/gaql_resources.txt`

This means the server currently behaves as a general Google Ads GAQL query layer, not a curated business-report API.

## How Your Repo Will Be Configured with MCP

This is an important distinction: your repo does not become "MCP-enabled" only by editing application code. The MCP integration has two layers:

- the MCP server setup
- the MCP client configuration

### Layer 1: MCP server setup inside or alongside the repo

This repository already acts as the MCP server codebase.

For local usage, the server is run from this repo using:

- `.venv` for Python dependencies
- `.env.local` for credentials and runtime variables
- `run-local.sh` to start the server
- `gcloud-local.sh` to manage repo-local Google auth state

In practical terms, this means your repo is configured to host the MCP server process itself.

### Layer 2: MCP client configuration outside the repo

Your MCP client is what actually connects to the server. This is usually configured outside the repo in a client settings file such as:

- `~/.claude/settings.json`
- `~/.gemini/settings.json`
- `.cursor/mcp.json`
- `.vscode/mcp.json`

That config points the client to this repo's local server command or HTTP endpoint.

Example local command-based configuration:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "/absolute/path/to/google-ads-mcp/.venv/bin/google-ads-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/google-ads-mcp/.gcloud/application_default_credentials.json",
        "GOOGLE_PROJECT_ID": "your-gcp-project-id",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your-developer-token"
      }
    }
  }
}
```

### What this means for your main application repo

If your separate application repo needs to "use MCP," the usual flow is:

1. keep Google Ads access logic inside this MCP server
2. configure the MCP client used by developers or agents
3. let your application workflows call approved MCP tools instead of directly querying Google Ads everywhere

This can be done in two ways:

### Option A: MCP is used only by developers or AI agents

In this model:

- your application code does not change much at first
- your MCP-enabled tooling connects to this Google Ads MCP server
- developers or agents use the server for reporting and analysis tasks

This is the fastest and lowest-risk rollout.

### Option B: Your application stack uses MCP as an internal service layer

In this model:

- your app or orchestration layer calls MCP tools as part of product workflows
- the MCP server becomes a controlled Google Ads data access layer
- custom tools can be added for approved business use cases

This is the better long-term architecture if you want controlled, reusable reporting access.

### Recommended configuration flow

If you move ahead, the repo-level configuration flow should be:

1. keep the MCP server code and local setup in this repo
2. keep secrets local and out of git
3. add MCP client config in the consuming environment, not in committed secret-bearing files
4. document which tools and report categories are allowed
5. only then decide whether your main application repo should call generic search or custom business-specific MCP tools

### What should be committed vs local-only

Safe to commit:

- documentation
- helper scripts
- example env templates
- ignore rules
- future custom tool code

Do not commit:

- `.env.local`
- `.gcloud/`
- `.venv/`
- real credentials or tokens

### Bottom line

Your repo will be configured with MCP through:

- local server setup in this repo
- external MCP client configuration that points to this repo's server
- optional future integration from your main application workflows into approved MCP tools

So the first configuration step is operational, not business-logic code changes.

## Chosen Access Model

The intended design model for this MCP server is:

- one credential
- multiple clients' data

More precisely:

- one shared Google credential authenticates the MCP server
- the MCP client passes `customer_id` dynamically per request
- the server returns data for whichever Google Ads client account that credential is authorized to access
- if access is through a manager account, `login_customer_id` provides the manager context

This means the access pattern is:

- shared authentication identity
- dynamic target account selection
- multiple client accounts behind one server

### Practical interpretation

In this model:

- `GOOGLE_APPLICATION_CREDENTIALS` identifies who is calling Google
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` identifies the manager account context, when needed
- `customer_id` identifies the client account whose data is being queried

### Important implication

Because one credential can potentially access multiple client accounts, this model should eventually include MCP-side restrictions such as:

- an allowlist of approved `customer_id`s
- optional filtering of `list_accessible_customers`
- query-level policy checks on allowed report categories

Without those restrictions, the MCP server may expose any account reachable by the shared credential.

## Detailed Flow Diagram

The following diagrams show how a request moves from an MCP client to Google Ads, where `customer_id` and `login_customer_id` are used, and where future restriction logic would sit.

### 1. High-Level MCP Flow

```text
+-------------------+
| MCP Client        |
| Claude/Cursor/etc |
+---------+---------+
          |
          | tool call
          | search(customer_id, resource, fields, ...)
          v
+---------+---------+
| MCP Server        |
| google-ads-mcp    |
+---------+---------+
          |
          | validates request
          | applies future policy rules
          v
+---------+---------+
| Google Ads Client |
| built from ADC    |
+---------+---------+
          |
          | Google Ads API request
          v
+---------+---------+
| Google Ads API    |
+---------+---------+
          |
          | GAQL results
          v
+---------+---------+
| MCP Server        |
| formats response  |
+---------+---------+
          |
          | MCP tool response
          v
+-------------------+
| MCP Client        |
+-------------------+
```

### 2. Account and Credential Flow

```text
+--------------------------------------------------------------+
| Local runtime config                                         |
| .env.local                                                   |
| - GOOGLE_APPLICATION_CREDENTIALS                             |
| - GOOGLE_ADS_LOGIN_CUSTOMER_ID (optional, usually MCC)       |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| ADC credentials                                               |
| application_default_credentials.json                          |
| "Who is calling Google?"                                      |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| MCP server request context                                    |
| - login_customer_id from env                                  |
| - customer_id passed dynamically by MCP client                |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------------------------------------------------+
| Google Ads request meaning                                    |
| login_customer_id = manager / access context                  |
| customer_id       = target ads account whose data is queried  |
+--------------------------------------------------------------+
```

### 3. Recommended Restriction Flow

```text
+--------------------+
| MCP Client         |
| passes customer_id |
+---------+----------+
          |
          v
+---------+----------+
| search tool        |
| ads_mcp/tools/     |
| search.py          |
+---------+----------+
          |
          | Step A: validate customer_id
          | - allowed account?
          | - approved child under MCC?
          |
          | Step B: validate query shape
          | - blocked resource?
          | - blocked segment?
          | - blocked combination?
          v
+---------+----------+
| allowed?           |
+----+-----------+---+
     |           |
   no|           |yes
     |           |
     v           v
+----+----+   +--+------------------+
| return  |   | execute Google Ads  |
| MCP     |   | API request         |
| error   |   +--+------------------+
+---------+      |
                 v
           +-----+------------------+
           | format and return data |
           +------------------------+
```

### 4. Future Curated Tool Flow

If you later add custom business-specific tools, the flow becomes more controlled:

```text
+----------------------+
| MCP Client           |
| calls approved tool  |
| e.g. search term     |
+----------+-----------+
           |
           v
+----------+-----------+
| Custom MCP Tool      |
| ads_mcp/tools/...    |
+----------+-----------+
           |
           | fixed resource mapping
           | fixed allowed metrics
           | fixed allowed segments
           v
+----------+-----------+
| internal GAQL query  |
+----------+-----------+
           |
           v
+----------+-----------+
| Google Ads API       |
+----------+-----------+
           |
           v
+----------------------+
| standard response    |
+----------------------+
```

### 5. End-to-End Decision Flow

This is the most practical way to think about the final design:

```text
1. Client authenticates to MCP environment
2. Client calls MCP tool
3. MCP server receives dynamic customer_id
4. MCP server applies account-level restrictions
5. MCP server applies report/query-level restrictions
6. If blocked, return MCP error
7. If allowed, build Google Ads request
8. Use ADC credentials for authentication
9. Use optional login_customer_id as manager context
10. Query target customer_id
11. Format results
12. Return approved data to client
```

### Where Each Concern Lives

```text
Authentication identity
  -> GOOGLE_APPLICATION_CREDENTIALS

Manager access context
  -> GOOGLE_ADS_LOGIN_CUSTOMER_ID

Dynamic target account
  -> customer_id passed to search/custom tool

Account allowlisting
  -> future validation layer in search.py / tool wrappers

Report-type restrictions
  -> future validation layer in search.py / tool wrappers

Approved business outputs
  -> future custom tools in ads_mcp/tools/
```

## What Is Already Available Today

These items are likely already available through the existing `search` tool, assuming the required Google Ads fields and metrics are supported by GAQL for the chosen resource:

- Impression Share
- Lost IS (Budget)
- Lost IS (Rank)
- Quality Score
- Keyword-level efficiency
- Search Term Report for negative keyword discovery
- Top-of-page rate
- Absolute top-of-page rate
- Audience analysis
- Change history
- Keywords
- Product catalog / shopping-style product reporting

These are likely partial or need validation:

- Reach & Frequency
- TAM / audience size

These are not clean first-class capabilities in the current MCP server and would likely need custom handling or may not be available directly:

- Ad Rank
- Reach / frequency union and overlap math
- Auction Insights

## Likely Resource Mapping

These are the main Google Ads resource families you would likely use for each need.

### Impression Share, Lost IS (Budget), Lost IS (Rank)

Potential resources:

- `campaign`
- `ad_group`
- `keyword_view`
- `ad_group_criterion`

### Quality Score and keyword-level efficiency

Potential resources:

- `keyword_view`
- `ad_group_criterion`

### Search Term Report

Potential resources:

- `search_term_view`
- `campaign_search_term_view`
- `customer_search_term_insight`
- `dynamic_search_ads_search_term_view`
- `smart_campaign_search_term_view`

### Top-of-page and absolute top-of-page rate

Potential resources:

- `keyword_view`
- `ad_group_criterion`
- `campaign`
- `ad_group`

### Audience analysis

Potential resources:

- `campaign_audience_view`
- `ad_group_audience_view`
- `audience`
- `combined_audience`
- `custom_audience`
- `user_list`

### Change history

Potential resource:

- `change_event`

### Keywords

Potential resources:

- `keyword_view`
- `ad_group_criterion`
- `display_keyword_view`

### Product catalog

Potential resources:

- `shopping_product`
- `shopping_performance_view`
- `product_group_view`
- `asset_group_product_group_view`

## What Should Be Limited

Since you already have campaign and ad-group daily/hourly reporting elsewhere, the MCP server should eventually avoid exposing those generic analytics patterns.

The main things to limit later are:

- generic `campaign` reporting
- generic `ad_group` reporting
- daily segmented reporting using `segments.date`
- hourly segmented reporting using `segments.hour`
- day-of-week breakdowns if those overlap with your current system
- broad metric exploration outside your approved use cases

## Recommended Implementation Strategy

The cleanest path is not to rely forever on unrestricted GAQL search. Instead, move in phases.

## Phase 1: Capability Validation

Before changing behavior, validate exactly which requested categories are truly available via Google Ads GAQL.

### Step 1

Use `get_resource_metadata` on the most relevant resources:

- `keyword_view`
- `ad_group_criterion`
- `search_term_view`
- `campaign_search_term_view`
- `campaign_audience_view`
- `ad_group_audience_view`
- `change_event`
- `shopping_product`
- `shopping_performance_view`
- `product_group_view`

Purpose:

- confirm that required metrics and segments exist
- confirm whether the fields you need are selectable and filterable

### Step 2

Create a business mapping sheet with these columns:

- requirement
- candidate resource
- candidate metrics
- candidate segments
- status
- notes

Status should be one of:

- available now
- available with custom wrapper
- partially available
- not available

### Step 3

Explicitly validate the uncertain cases:

- Ad Rank
- Auction Insights
- Reach & Frequency
- TAM / audience size
- Reach/frequency overlap math

These should not be assumed to exist until validated.

## Phase 2: Define the Allowed Scope

Once capability validation is done, define what the MCP server is allowed to expose.

### Step 4

Create an allowlist of approved reporting categories:

- keyword insights
- search term analysis
- audience analysis
- change history
- product and shopping reporting
- impression-share-style metrics

### Step 5

Create a denylist of broad reporting categories that should not be exposed:

- generic campaign reporting
- generic ad-group reporting
- daily campaign insights
- hourly campaign insights
- daily ad-group insights
- hourly ad-group insights

### Step 6

Define whether the denylist should block:

- resources
- segments
- metrics
- or combinations of all three

In practice, combination-based blocking is usually best. For example:

- allow `campaign` only for impression-share-related queries
- block `campaign` when combined with `segments.date`
- block `ad_group` when combined with `segments.hour`

## Phase 3: Decide the Product Shape

You have two design options.

### Option A: Restrict the generic `search` tool

This keeps the current architecture but adds safety rules.

What would change:

- parse inputs to the `search` tool
- reject disallowed resources
- reject disallowed segments
- reject disallowed combinations
- return a clear MCP error message when a blocked query is attempted

Best file for this:

- `ads_mcp/tools/search.py`

### Option B: Add custom purpose-built tools

This is the cleaner long-term design if you want predictable outputs for downstream agents or application workflows.

Examples of future tools:

- `get_impression_share_report`
- `get_keyword_efficiency_report`
- `get_search_term_discovery_report`
- `get_audience_analysis_report`
- `get_change_history_report`
- `get_product_catalog_report`

What would change:

- add new files under `ads_mcp/tools/`
- register them via imports in `ads_mcp/server.py`
- optionally reduce or hide generic search from some environments

Recommended approach:

- use both
- keep `search` but restrict it
- add custom tools for the highest-value business reports

## Phase 4: Implement Restrictions

If you choose to limit generic access, these are the step-by-step code changes.

### Step 7

Add a policy layer in `ads_mcp/tools/search.py`.

The policy should inspect:

- `resource`
- `fields`
- `conditions`
- `orderings`

It should decide whether the query is:

- allowed
- blocked
- allowed only for specific metric patterns

### Step 8

Create explicit validation rules such as:

- block `campaign` with `segments.date`
- block `campaign` with `segments.hour`
- block `ad_group` with `segments.date`
- block `ad_group` with `segments.hour`
- allow `keyword_view` for quality score and efficiency metrics
- allow `search_term_view` for discovery use cases
- allow `change_event`
- allow audience view resources
- allow shopping/product resources

### Step 9

Add human-readable error messages when a query is blocked.

Examples:

- "Generic campaign daily insights are not available through this MCP server."
- "Use the keyword or search term reporting tools for this use case."

### Step 10

Optionally restrict metadata discovery in `ads_mcp/tools/get_resource_metadata.py` so agents cannot freely discover resources you intend to block.

Without this step, an agent may still see blocked resources even if it cannot query them.

## Phase 5: Add Custom Reporting Tools

If you decide to create a more curated interface, use these steps.

### Step 11

Create one tool per business capability group instead of one tool per metric.

Suggested grouping:

- keyword and competitiveness insights
- search term discovery
- audience analysis
- change history
- product and catalog reporting

### Step 12

For each tool, define:

- required inputs
- allowed segments
- allowed filters
- default date range behavior
- output shape

Example for search term discovery:

- input: `customer_id`, date range, campaign filter, ad group filter
- output: search terms, impressions, clicks, cost, conversions, CTR, match context
- guardrail: no unrelated generic campaign reporting

### Step 13

Register these new tools in `ads_mcp/server.py`.

## Phase 6: Handle the Uncertain or Advanced Requests

These need special treatment.

### Ad Rank

Treat this as unconfirmed until proven available from Google Ads fields you can access through GAQL. If not directly available, document it as unsupported.

### Auction Insights

Treat this as unconfirmed until validated. If Google Ads does not expose it in the form you need through GAQL, it should be marked unsupported in the MCP server.

### Reach & Frequency

Validate first. If partially available, it may need a dedicated wrapper tool that standardizes the available fields and explains limitations.

### Reach / frequency union and overlap math

This is likely not a raw Google Ads resource output. It probably belongs in:

- a custom analytics layer
- or a custom MCP tool that combines multiple source queries and computes derived results

### TAM / audience size

This may depend on your exact meaning of TAM. If it maps to available audience-size-style data, it may be partially supported. If it requires planning or forecasting semantics, it may need a dedicated derived tool.

## Phase 7: Testing Plan

Once implementation starts, validate behavior in layers.

### Step 14

Add unit tests for any query restriction logic.

Likely test file location:

- `tests/tools/`

### Step 15

Add tool-level tests for each custom reporting tool that is introduced.

### Step 16

Add smoke tests for:

- allowed keyword reports
- allowed search term reports
- allowed audience reports
- blocked campaign daily reports
- blocked ad-group hourly reports

## Suggested Deliverables

If you move ahead, the implementation should probably produce:

### Deliverable 1

A capability matrix that says:

- requirement
- supported now
- supported after wrapper
- unsupported

### Deliverable 2

A restriction policy for generic search.

### Deliverable 3

Custom MCP tools for the highest-priority approved use cases.

### Deliverable 4

Tests covering both allowed and blocked scenarios.

## Recommended Order of Work

If you want the safest rollout, do the work in this order:

1. Validate exact field support using `get_resource_metadata`
2. Create the capability matrix
3. Finalize the allowlist and denylist
4. Restrict generic `search`
5. Add custom tools for approved report families
6. Add tests
7. Update docs for client usage

## Final Recommendation

Do not start by building everything as one open-ended search surface.

A better approach is:

- validate what Google Ads truly supports
- restrict generic campaign/ad-group daily/hourly exploration
- keep keyword, search term, audience, change history, and product reporting
- add custom tools for the business flows you care about most

That gives you a more controlled MCP server and avoids overlapping with analytics you already have.
