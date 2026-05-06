# MCP Capabilities for Requested Google Ads Data

This document summarizes what is currently available from this repository's MCP server without changing its behavior.

## Important Context

This server does not expose a separate MCP tool for each business report. It mainly exposes:

- `search`: run Google Ads GAQL queries
- `get_resource_metadata`: discover fields, metrics, and segments allowed for a resource
- `list_accessible_customers`: list available customer IDs

That means most reporting needs are supported only if the underlying Google Ads API resource and metrics are queryable through GAQL.

## Current MCP Tools

The current MCP tools are defined in:

- `ads_mcp/tools/search.py`
- `ads_mcp/tools/get_resource_metadata.py`
- `ads_mcp/tools/core.py`

The server registers them through:

- `ads_mcp/server.py`

## Requested Items: Availability Summary

### Likely available now through the existing `search` tool

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
- Product catalog / shopping-related product reporting

### Likely partial, derived, or dependent on exact Google Ads field support

- Reach & Frequency
- TAM / audience size

### Likely not directly available as a clean first-class output today

- Ad Rank
- Reach / frequency union & overlap math
- Auction Insights

## Why These Are the Answers

The server is backed by GAQL resources listed in:

- `ads_mcp/gaql_resources.txt`

That file already includes relevant resource families such as:

- `keyword_view`
- `ad_group_criterion`
- `search_term_view`
- `campaign_search_term_view`
- `customer_search_term_insight`
- `change_event`
- `audience`
- `ad_group_audience_view`
- `campaign_audience_view`
- `user_list`
- `shopping_product`
- `shopping_performance_view`
- `product_group_view`
- `asset_group_product_group_view`

Because these resources already exist in the MCP server's valid-resource list, they are the strongest indicators that the current `search` tool can be used for those categories.

## Mapping Your Requirements to Likely Resources

### Impression Share, Lost IS (Budget), Lost IS (Rank)

Likely queryable through campaign-, ad-group-, or keyword-related GAQL resources using compatible `metrics.*` fields.

Potential resource families:

- `campaign`
- `ad_group`
- `keyword_view`
- `ad_group_criterion`

### Quality Score and keyword-level efficiency

Likely queryable from keyword-related resources.

Potential resource families:

- `keyword_view`
- `ad_group_criterion`

Typical efficiency metrics would also come from compatible `metrics.*` fields such as clicks, cost, CTR, conversions, CPC, and related measures.

### Search Term Report for negative keyword discovery

Strong fit for the current MCP server.

Potential resource families:

- `search_term_view`
- `campaign_search_term_view`
- `customer_search_term_insight`
- `dynamic_search_ads_search_term_view`
- `smart_campaign_search_term_view`

### Top-of-page / Abs-top-of-page rate

Likely available through keyword or campaign reporting resources where those metrics are compatible.

Potential resource families:

- `keyword_view`
- `ad_group_criterion`
- `campaign`
- `ad_group`

### Audience analysis

Likely available now through audience-oriented resources.

Potential resource families:

- `campaign_audience_view`
- `ad_group_audience_view`
- `audience`
- `combined_audience`
- `custom_audience`
- `user_list`

### Change history

Strong fit for the current MCP server.

Potential resource family:

- `change_event`

### Reach & Frequency

Possibly partial depending on which fields Google Ads exposes through GAQL for the relevant resources. This likely needs validation against `get_resource_metadata` for the exact resource you want to use.

### Reach / frequency union & overlap math

Not likely to be a built-in Google Ads API report exposed directly by this MCP server. This sounds more like downstream analysis that would need:

- multiple source queries
- custom aggregation logic
- possibly a custom MCP tool or external analytics layer

### Auction Insights

Not currently represented as a dedicated MCP tool in this repository. If Google Ads exposes some related data indirectly, it is not modeled here as an opinionated report today.

### Keywords

Strong fit for the current MCP server.

Potential resource families:

- `keyword_view`
- `ad_group_criterion`
- `display_keyword_view`

### Product catalog

Likely available for shopping / product reporting use cases.

Potential resource families:

- `shopping_product`
- `shopping_performance_view`
- `product_group_view`
- `asset_group_product_group_view`

### TAM / audience size

This may be partially available depending on whether your intended notion of TAM maps to Google Ads audience resources and fields. It is not currently represented as a dedicated, ready-made MCP output in this repository.

## Generic Reporting That Is Also Broadly Available

Because this MCP server exposes a generic GAQL `search` tool, it can potentially query much more than the items you listed, including:

- campaign reporting
- ad group reporting
- ad reporting
- asset reporting
- keyword reporting
- audience reporting
- placement reporting
- landing page reporting
- geographic reporting
- device reporting
- demographic reporting
- shopping and product reporting
- recommendations
- bidding entities
- conversion-related entities
- experiments and drafts

This is why limiting scope matters if you only want a subset of reporting exposed.

## If You Want to Limit What the MCP Server Can Return Later

No changes have been made for this yet. If you decide to restrict behavior later, the main places would be:

### Primary enforcement point

- `ads_mcp/tools/search.py`

This is the best place to:

- block certain resources
- block certain segments such as date/hour/day breakdowns
- block resource and metric combinations
- enforce an allowlist of approved reporting categories

### Metadata visibility control

- `ads_mcp/tools/get_resource_metadata.py`

This is the place to limit what field metadata the MCP server reveals if you do not want agents discovering blocked resources or blocked fields.

### Opinionated custom tools

If you later want fixed-purpose tools such as:

- `get_keyword_insights`
- `get_search_term_report`
- `get_audience_analysis`
- `get_change_history`

those would be added under:

- `ads_mcp/tools/`

and imported from:

- `ads_mcp/server.py`

## Recommended Future Shape

If your goal is controlled exposure instead of open-ended GAQL querying, a good future structure would be:

- allow keyword/search-term/audience/change-history/product use cases
- block generic campaign and ad-group daily/hourly reporting if you already have that elsewhere
- expose a small number of custom MCP tools for the approved business reports

That would make the server safer and easier for downstream agents to use consistently.

## Bottom Line

### Available now

- most keyword, search term, audience, change history, and product-related reporting
- impression share and related competitive delivery metrics, if exposed as compatible Google Ads metrics on supported resources

### Partially available or needs validation

- reach and frequency
- TAM / audience size

### Not cleanly available as a ready-made MCP capability today

- ad rank
- auction insights
- reach/frequency union and overlap math

## Reference Files

- `ads_mcp/tools/search.py`
- `ads_mcp/tools/get_resource_metadata.py`
- `ads_mcp/tools/core.py`
- `ads_mcp/server.py`
- `ads_mcp/gaql_resources.txt`
