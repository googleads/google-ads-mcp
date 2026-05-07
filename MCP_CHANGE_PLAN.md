# MCP Change Plan for Required Google Ads Reporting

## Goal

Support curated Google Ads reporting for these use cases while blocking generic daily/hourly campaign and ad-group reporting that already exists in the existing analytics stack:

- Impression Share, Lost IS (Budget), Lost IS (Rank)
- Quality Score, Ad Rank, keyword-level efficiency
- Search Term Report — negative keyword discovery
- Top-of-page rate / Absolute top-of-page rate
- Audience analysis
- Change history
- Reach & Frequency
- Reach / frequency union & overlap math
- Auction Insights
- Keywords
- Product catalog
- TAM / audience size

---

## Validated Capability Matrix (2026-05-06)

All items below were validated against the live Google Ads API using `get_resource_metadata` and real account data.

| # | Requirement | Status | Resource(s) | Key Fields |
|---|---|---|---|---|
| 1 | Impression Share | Available now | `keyword_view`, `campaign`, `ad_group` | `metrics.search_impression_share`, `metrics.search_exact_match_impression_share`, `metrics.search_absolute_top_impression_share` |
| 2 | Lost IS (Budget) | Available now | `keyword_view`, `campaign`, `ad_group` | `metrics.search_budget_lost_impression_share`, `metrics.search_budget_lost_top_impression_share`, `metrics.search_budget_lost_absolute_top_impression_share` |
| 3 | Lost IS (Rank) | Available now | `keyword_view`, `campaign`, `ad_group` | `metrics.search_rank_lost_impression_share`, `metrics.search_rank_lost_top_impression_share`, `metrics.search_rank_lost_absolute_top_impression_share` |
| 4 | Quality Score | Available now | `ad_group_criterion` | `ad_group_criterion.quality_info.quality_score`, `.creative_quality_score`, `.post_click_quality_score`, `.search_predicted_ctr`; also `metrics.historical_quality_score` on `keyword_view` |
| 5 | Ad Rank | Not directly available | — | Not a GAQL field. Use Quality Score + IS (rank lost) as a composite proxy. |
| 6 | Keyword-level efficiency | Available now | `keyword_view`, `ad_group_criterion` | `metrics.impressions`, `metrics.clicks`, `metrics.ctr`, `metrics.cost_micros`, `metrics.conversions`, `metrics.cost_per_conversion` |
| 7 | Search Term Report (negative kw discovery) | **Done — custom tool built** | `search_term_view` | See `get_search_term_report` below |
| 8 | Top-of-page rate | Available now | `keyword_view`, `campaign`, `ad_group`, `search_term_view` | `metrics.top_impression_percentage`, `metrics.search_top_impression_share` |
| 9 | Absolute top-of-page rate | Available now | same as above | `metrics.absolute_top_impression_percentage`, `metrics.search_absolute_top_impression_share` |
| 10 | Audience analysis | Available now | `campaign_audience_view`, `ad_group_audience_view`, `user_list` | Standard performance metrics on audience views; `user_list.description`, `audience.name` |
| 11 | Change history | Available now | `change_event` | `change_event.change_date_time`, `.change_resource_type`, `.resource_change_operation`, `.changed_fields`, `.new_resource`, `.old_resource`, `.user_email` — note: LIMIT ≤ 10000 required |
| 12 | Reach & Frequency | Partial | `campaign`, `ad_group` | Standard impression metrics available everywhere. True `metrics.reach` exists only for Video/Display campaign types, not Search. |
| 13 | Reach/frequency union & overlap math | Not available as raw output | — | No GAQL resource exposes overlap math. Requires a custom derived tool that queries multiple audience sizes and computes intersection/union in Python. |
| 14 | Auction Insights | Available now | `keyword_view`, `campaign`, `ad_group` | `metrics.auction_insight_search_impression_share`, `metrics.auction_insight_search_overlap_rate`, `metrics.auction_insight_search_outranking_share`, `metrics.auction_insight_search_position_above_rate`, `metrics.auction_insight_search_top_impression_percentage`, `metrics.auction_insight_search_absolute_top_impression_percentage` |
| 15 | Keywords | Available now | `keyword_view`, `ad_group_criterion` | Full keyword attributes + all efficiency and IS metrics |
| 16 | Product catalog | Available now | `shopping_performance_view`, `shopping_product`, `product_group_view` | IS metrics confirmed on `shopping_performance_view`; product attributes on `shopping_product` |
| 17 | TAM / audience size | Partial | `user_list` | `user_list.size_for_search`, `user_list.size_range_for_search`, `user_list.size_for_display`, `user_list.size_range_for_display` — confirmed available. TAM as a planning/forecasting concept is not in GAQL. |

---

## Generic Reporting to Block

These patterns are available in the current `search` tool but overlap with the existing analytics stack. A policy layer in `search.py` should block them:

| Block pattern | Reason |
|---|---|
| `campaign` + `segments.date` | Daily campaign performance — already covered |
| `campaign` + `segments.hour` | Hourly campaign performance — already covered |
| `ad_group` + `segments.date` | Daily ad group performance — already covered |
| `ad_group` + `segments.hour` | Hourly ad group performance — already covered |
| `ad_group` + `segments.day_of_week` | Day-of-week ad group breakdown — already covered |

**Exception:** `campaign` and `ad_group` queries that select IS, Quality Score, or Auction Insight metrics must remain allowed even if they include `segments.date`. These are additive, not overlapping.

---

## Account Structure

The credential authenticates as top-level MCC `5061122756`. All data queries must target a **leaf client account** (a non-manager account under the MCC hierarchy).

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` must be set to the MCC ID without hyphens: `5061122756`
- `customer_id` passed to each tool must be a leaf account ID (e.g. `1673268103`, `1635583349`)
- `list_accessible_customers` returns top-level MCC IDs only, not the leaf accounts
- Use the `customer_client` resource on the MCC to enumerate leaf accounts:

```
SELECT customer_client.client_customer, customer_client.level,
       customer_client.manager, customer_client.descriptive_name
FROM customer_client
WHERE customer_client.level <= 2
```

---

## Code Changes

### Done

**`ads_mcp/tools/search_term_report.py`** — new file

Custom MCP tool `get_search_term_report`. Fixed to the `search_term_view` resource. Inputs: `customer_id`, `start_date`, `end_date`, optional `campaign_id`, `ad_group_id`, `min_impressions`, `limit`. Returns clean named fields per row: `search_term`, `status`, `triggering_keyword`, `match_type`, `impressions`, `clicks`, `ctr`, `cost_micros`, `conversions`, `top_impression_pct`, `abs_top_impression_pct`. Live-tested against real accounts.

**`ads_mcp/server.py`** — one line added

```python
from ads_mcp.tools import search, core, get_resource_metadata, search_term_report  # noqa: F401
```

**`.mcp.json`** — new file at repo root

Registers the MCP server with Claude Code so the tool is callable from the IDE:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "/absolute/path/to/.venv/bin/google-ads-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "...",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "...",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "5061122756"
      }
    }
  }
}
```

### Remaining — Custom Tools

| Tool | File | Resource | Status |
|---|---|---|---|
| `get_keyword_quality_report` | `ads_mcp/tools/keyword_quality.py` | `ad_group_criterion` + `keyword_view` | Not started |
| `get_auction_insights_report` | `ads_mcp/tools/auction_insights.py` | `keyword_view` / `campaign` | Not started |
| `get_audience_analysis_report` | `ads_mcp/tools/audience_analysis.py` | `campaign_audience_view`, `user_list` | Not started |
| `get_change_history_report` | `ads_mcp/tools/change_history.py` | `change_event` | Not started |
| `get_impression_share_report` | `ads_mcp/tools/impression_share.py` | `keyword_view`, `campaign` | Not started |

### Remaining — Policy Layer

Add a validation function at the top of `ads_mcp/tools/search.py` that inspects `resource`, `fields`, and `conditions` before executing the query. Block combinations listed in the table above. Return a clear error message naming what is blocked and why.

---

## Relevant Files

| File | Purpose |
|---|---|
| `ads_mcp/server.py` | Entry point — import new tool modules here to register them |
| `ads_mcp/tools/search.py` | Generic GAQL tool — policy layer goes here |
| `ads_mcp/tools/search_term_report.py` | Search term report tool — done |
| `ads_mcp/tools/core.py` | `list_accessible_customers` |
| `ads_mcp/tools/get_resource_metadata.py` | Field discovery |
| `ads_mcp/gaql_resources.txt` | Allowlist of valid GAQL resources exposed to `search` |
| `.mcp.json` | Claude Code MCP client config |
| `.env.local` | Local credentials — not committed |
