# Google Ads MCP Server

A Google Ads [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for querying accounts, creating selected assets, managing labels, and running guarded campaign mutations. This fork adds multi-account credential routing, campaign reporting workflows, and checksum-backed confirmation for every mutation.

## What It Provides

The server exposes Google Ads capabilities as MCP tools for AI clients. Read tools query the Google Ads API directly. Mutation tools begin with a dry-run proposal and require a matching checksum after explicit user approval before committing.

### Read Tools

- `list_accessible_customers`: Lists customer IDs directly accessible to selected credentials.
- `search`: Runs structured Google Ads Query Language (GAQL) queries.
- `get_resource_metadata`: Returns valid fields and metadata for a Google Ads resource.
- `campaign_diagnostics`: Returns campaign status, budget, bidding, spend, clicks, and conversions.
- `search_term_report`: Returns search terms and campaign performance.
- `budget_report`: Returns campaign budget and delivery data.
- `conversion_report`: Returns campaign conversion volume, value, and cost metrics.
- `performance_anomalies`: Detects day-over-day campaign metric changes above a requested threshold.

### Mutation Tools

- `create_asset`: Creates text, image, YouTube video, sitelink, callout, structured-snippet, and supported custom assets.
- `upload_video_asset`: Uploads a local video through the Google Ads API in local `stdio` mode.
- `manage_labels`: Creates, updates, and removes account labels.
- `manage_label_associations`: Adds or removes labels on campaigns, customers, ad groups, and ad group criteria.
- `manage_campaign`: Creates a basic campaign with its initial budget, updates its name or status, or removes it.

## Mutation Safety

Every mutation tool follows a two-step process:

1. Call it with `validate_only=true` (the default). The server validates the request and returns readable `change_items` plus a checksum.
2. Present the proposal to the user and obtain explicit approval.
3. Call the same tool with `validate_only=false`, unchanged parameters, and the returned checksum.

The checksum is bound to the customer ID and operation payload, preventing accidental parameter changes between validation and commit. It does not replace account authorization.

## Current Limits

This fork does **not** currently create or manage ad groups, ads, keywords, targeting, bidding strategies, campaign-level negative keywords, or asset associations. `manage_campaign` intentionally supports only the basic campaign fields listed above; advanced channel-specific campaign configuration is not yet exposed.

## Requirements

- Python 3.10 or later.
- A Google Cloud project with the Google Ads API enabled.
- Google Ads API credentials and, where required, a developer token.
- Access to the target Google Ads customer account.

## Install and Run

    git clone https://github.com/suryakantgaat-dotcom/google-ads-mcp.git
    cd google-ads-mcp
    python -m venv .venv
    .venv/bin/pip install .
    .venv/bin/google-ads-mcp

The default transport is `stdio`. Setting both
`GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` and
`GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` switches the server to Streamable HTTP
on `PORT` (default `8080`).

## Authentication

For a single default account, configure one supported mode:

- **MCP OAuth:** Set `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` and
  `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET`. In HTTP mode, the server uses
  FastMCP's Google OAuth provider.
- **Refresh token:** Set `GOOGLE_ADS_REFRESH_TOKEN` with
  `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` and
  `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET`.
- **Application Default Credentials:** Set `GOOGLE_ADS_MCP_ALLOW_ADC=true`,
  then configure ADC with the Google Ads OAuth scope.

Set `GOOGLE_ADS_DEVELOPER_TOKEN` when your account requires a developer
token. Use `GOOGLE_ADS_LOGIN_CUSTOMER_ID` for a default manager-account
header.

### Multi-Account Routing

Set `GOOGLE_ADS_ACCOUNTS_CONFIG` to a JSON array of named account
configurations. Each entry supplies its own credentials and developer token:

    [
      {
        "name": "client_a",
        "developer_token": "YOUR_TOKEN",
        "login_customer_id": "1234567890",
        "refresh_token": "REFRESH_TOKEN",
        "client_id": "OAUTH_CLIENT_ID",
        "client_secret": "OAUTH_CLIENT_SECRET"
      }
    ]

Pass `account_name: "client_a"` to a tool call to select that configuration.
A supplied `login_customer_id` tool parameter overrides the account
configuration.

## Tool Configuration

`tools_config.yaml` controls which namespaces are mounted and their prefixes.
It resolves in this order:

1. The path in `GOOGLE_ADS_MCP_TOOLS_CONFIG`.
2. `tools_config.yaml` in the process working directory.
3. The bundled default configuration.

The bundled configuration exposes unprefixed tool names. To run read-only,
explicitly enable the read namespaces and disable mutation namespaces:

    namespaces:
      customers: ""
      search: ""
      metadata: ""
      reporting: ""
      assets: false
      labels: false
      campaigns: false

When `namespaces` is non-empty, any namespace omitted from the file is
disabled.

## Resources

The server also exposes these reference resources:

- `resource://discovery-document`
- `resource://metrics`
- `resource://segments`
- `resource://release-notes`

## Google Ads AI Helpers

[Google Ads API AI agent skills](https://developers.google.com/google-ads/api/docs/developer-toolkit/agent-skills)
can help an AI coding agent construct valid GAQL, configure credentials, and
follow API practices. They do not grant account access or bypass this server's
confirmation flow.

The Google Ads API Developer Assistant is a separate development plugin for
schema inspection, GAQL validation, and code generation. It is not part of this
server and does not provide live Google Ads access.

## Contributing

Run the test suite with:

    .venv/bin/python -m unittest discover --buffer -s tests -p '*_test.py'

Never commit credentials, refresh tokens, developer tokens, or OAuth client
secrets.
