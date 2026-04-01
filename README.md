# Google Ads MCP Server — Autonomous AI Agent for Google Ads Management

> **Give Claude, Gemini, or any MCP-compatible AI agent full control over your Google Ads account.**  
> 65+ tools across 8 modules. Built on Google Ads Python API v23. Apache 2.0 licensed.

[![GitHub Stars](https://img.shields.io/github/stars/hemangjoshi37a/hjLabs.in-google-ads-mcp?style=social)](https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp/stargazers)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Google Ads API v23](https://img.shields.io/badge/Google%20Ads%20API-v23-green)](https://developers.google.com/google-ads/api/reference/rpc/v23/overview)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple)](https://modelcontextprotocol.io)

---

## What Is This?

This is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that connects AI assistants like **Claude**, **Gemini**, and **GitHub Copilot** directly to the [Google Ads API](https://developers.google.com/google-ads/api). Instead of manually navigating the Google Ads dashboard, you describe what you want in natural language — and the AI executes it.

**Before:** Open dashboard → navigate menus → export CSVs → copy-paste keywords → adjust bids manually → repeat.

**After:** *"Check which keywords have quality score below 5, pause them, and add the top 10 converting search terms as exact-match keywords."* → Done.

### Works With
- ✅ [Claude Desktop](https://claude.ai/download) (Anthropic)
- ✅ [Claude Code](https://claude.ai/code) (CLI)
- ✅ [Gemini CLI](https://github.com/google-gemini/gemini-cli)
- ✅ [Gemini Code Assist](https://marketplace.visualstudio.com/items?itemName=Google.geminicodeassist) (VS Code)
- ✅ Any MCP-compatible agent or framework

---

## Table of Contents

- [Features & Tools](#features--tools-65-total)
- [Quick Start](#quick-start)
- [Installation](#installation)
  - [Option A: Claude Desktop / Claude Code](#option-a-claude-desktop--claude-code)
  - [Option B: Gemini CLI / Code Assist](#option-b-gemini-cli--code-assist)
  - [Option C: Run Locally (pip install)](#option-c-run-locally-pip-install)
- [Authentication](#authentication)
  - [OAuth Refresh Token (Recommended)](#option-1-oauth-refresh-token-recommended)
  - [Application Default Credentials](#option-2-application-default-credentials-adc)
  - [google-ads.yaml (Python Client Library)](#option-3-google-adsyaml-python-client-library)
- [Environment Variables](#environment-variables)
- [Manager Account (MCC) Support](#manager-account-mcc-support)
- [Sample Prompts](#sample-prompts)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

---

## Features & Tools (65+ total)

### 🧾 Billing & Account Spend
Track your Google Ads balance, payment method status, and spend trends without opening the UI.

| Tool | Description |
|------|-------------|
| `get_billing_info` | Billing setup, approved budget, amount served, estimated remaining balance |
| `get_account_spend_summary` | Total spend/clicks/conversions across all campaigns for any date range |
| `get_daily_spend_trend` | Day-by-day burn rate for the last N days |

### 📊 Advanced Analytics
Deep performance analysis by device, location, hour of day, and competitor positioning.

| Tool | Description |
|------|-------------|
| `get_device_performance` | Performance by device: MOBILE, DESKTOP, TABLET |
| `get_geo_performance` | Clicks, spend, conversions by geographic location |
| `get_hourly_performance` | Hour × day-of-week heatmap (find peak hours for ad scheduling) |
| `get_quality_scores` | Quality Score (1-10), Expected CTR, Ad Relevance, Landing Page Experience per keyword |
| `get_auction_insights` | Competitor domains, impression share overlap, outranking share |
| `get_search_impression_share` | Lost IS due to budget vs. rank; top and abs-top impression share |

### 💰 Bidding Strategies
Switch bidding strategies in a single conversation — from manual CPC to smart bidding and back.

| Tool | Description |
|------|-------------|
| `set_target_cpa` | Switch to Target CPA smart bidding |
| `set_maximize_conversions` | Maximize conversions within budget (optional Target CPA constraint) |
| `set_maximize_conversion_value` | Maximize conversion value / ROAS (optional Target ROAS) |
| `set_manual_cpc` | Revert to Manual CPC with optional Enhanced CPC |
| `set_target_impression_share` | Visibility-based bidding: ANYWHERE, TOP_OF_PAGE, ABS_TOP_OF_PAGE |
| `update_keyword_bids_bulk` | Update CPC bids for multiple keywords in a single API call |

### 💡 Keyword Planning & Research
Run the Google Keyword Planner without leaving your AI chat.

| Tool | Description |
|------|-------------|
| `get_keyword_ideas` | Search volume, competition, and top-of-page bid range for seed keywords |
| `get_keyword_forecast` | Traffic/spend/conversion forecast for a keyword set at a given budget and bid |

### 📋 Recommendations
Fetch and act on Google's automated account recommendations without touching the UI.

| Tool | Description |
|------|-------------|
| `list_recommendations` | All pending Google Ads automated recommendations with estimated impact deltas |
| `apply_recommendation` | Apply a specific recommendation by resource name |
| `dismiss_recommendation` | Dismiss one or more irrelevant recommendations |

### 🎯 Campaign Management

| Tool | Description |
|------|-------------|
| `create_campaign_budget` | Create a shared daily budget |
| `update_campaign_budget` | Change a campaign's daily budget amount |
| `create_search_campaign` | Create a Search campaign with Target Spend bidding |
| `update_campaign_status` | Enable or pause a campaign |
| `remove_campaign` | Permanently remove a campaign |
| `list_campaigns` | List all campaigns with status, budget, and resource names |
| `get_campaign_performance` | Clicks, impressions, cost, and conversions per campaign |

### 📍 Geo Targeting

| Tool | Description |
|------|-------------|
| `suggest_geo_targets` | Look up geo target constant IDs by location name and country code |
| `add_geo_targets` | Add location targets to a campaign |

### 🗂 Ad Groups

| Tool | Description |
|------|-------------|
| `create_ad_group` | Create an ad group with CPC bid |
| `update_ad_group` | Rename an ad group |
| `update_ad_group_status` | Enable or pause an ad group |
| `update_ad_group_bid` | Update default CPC bid for an ad group |
| `set_ad_schedule` | Set dayparting schedules (replaces existing schedule atomically) |
| `list_ad_groups` | List all ad groups in a campaign |
| `get_ad_group_performance` | Per-ad-group performance breakdown |

### 🔑 Keywords

| Tool | Description |
|------|-------------|
| `add_keywords` | Add keywords with match type to an ad group |
| `add_negative_keywords` | Add negative keywords to an ad group |
| `add_campaign_negative_keywords` | Add campaign-level negative keywords |
| `add_search_terms_as_keywords` | Convert top-performing search terms directly into keywords |
| `update_keyword_status` | Enable, pause, or remove a keyword |
| `update_keyword_bid` | Update keyword-level CPC bid |
| `update_keyword_bids_bulk` | Batch update bids for multiple keywords in one API call |
| `list_keywords` | List all keywords in an ad group |
| `get_keyword_performance` | Per-keyword with quality score and impression share |
| `get_search_terms_report` | Actual search queries that triggered your ads |

### 📝 Ads (Responsive Search Ads)

| Tool | Description |
|------|-------------|
| `create_responsive_search_ad` | Create RSA with headlines, descriptions, and display URL paths |
| `list_ads` | List ads with approval status and ad strength |
| `update_ad_status` | Enable, pause, or remove a specific ad |
| `get_ad_performance` | Per-ad metrics with ad strength and approval status |

### 🔗 Assets & Asset Linking
Create ad extensions (Assets) and attach them to campaigns, ad groups, or entire accounts.

| Tool | Description |
|------|-------------|
| `create_sitelink_asset` | Sitelink with display text, descriptions, and optional date range |
| `create_callout_asset` | Short callout text (e.g., "Free Consultation", "24-Hour Support") |
| `create_structured_snippet_asset` | Header + values list (e.g., Services: RAG, LLM, MLOps) |
| `create_call_asset` | Phone number with call conversion reporting |
| `create_image_asset` | Image from URL or local file path |
| `create_promotion_asset` | Sale/offer with percent-off or money-off |
| `create_price_asset` | Pricing table with up to 8 offerings |
| `create_lead_form_asset` | In-ad lead capture form |
| `create_text_asset` | Text for Performance Max asset groups |
| `create_youtube_video_asset` | YouTube video asset by video ID |
| `link_asset_to_campaign` | Attach any asset to a campaign by field type |
| `link_asset_to_ad_group` | Attach any asset to an ad group |
| `link_assets_to_customer` | Attach assets at account level (applies to all campaigns) |
| `remove_campaign_asset` | Unlink an asset from a campaign |

### 🔄 Conversions

| Tool | Description |
|------|-------------|
| `create_conversion_action` | Create a webpage conversion action |
| `list_conversion_actions` | List all conversion actions with tag snippet details |

### 🔍 Search & Discovery

| Tool | Description |
|------|-------------|
| `search` | Run any GAQL query against the Google Ads API directly |
| `list_accessible_customers` | List all customer accounts accessible to the authenticated user |
| `get_resource_metadata` | Inspect available fields and resources in the Google Ads API |

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git
cd hjLabs.in-google-ads-mcp

# 2. Install
pip install -e .

# 3. Set your credentials (see Authentication section below)
export GOOGLE_ADS_DEVELOPER_TOKEN="your_developer_token"
export GOOGLE_ADS_REFRESH_TOKEN="your_refresh_token"
export GOOGLE_ADS_CLIENT_ID="your_client_id"
export GOOGLE_ADS_CLIENT_SECRET="your_client_secret"

# 4. Run the server
python -m ads_mcp.server
```

---

## Installation

### Option A: Claude Desktop / Claude Code

Add this to your Claude Desktop config:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "python",
      "args": ["-m", "ads_mcp.server"],
      "cwd": "/path/to/hjLabs.in-google-ads-mcp",
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
        "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
        "GOOGLE_ADS_CLIENT_ID": "YOUR_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET": "YOUR_CLIENT_SECRET"
      }
    }
  }
}
```

Or using `pipx` (no local clone needed):

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": [
        "run",
        "--spec",
        "git+https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git",
        "google-ads-mcp"
      ],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
        "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
        "GOOGLE_ADS_CLIENT_ID": "YOUR_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET": "YOUR_CLIENT_SECRET"
      }
    }
  }
}
```

### Option B: Gemini CLI / Code Assist

Create or edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": [
        "run",
        "--spec",
        "git+https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git",
        "google-ads-mcp"
      ],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
        "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
        "GOOGLE_ADS_CLIENT_ID": "YOUR_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET": "YOUR_CLIENT_SECRET",
        "GOOGLE_CLOUD_PROJECT": "YOUR_PROJECT_ID"
      }
    }
  }
}
```

### Option C: Run Locally (pip install)

```bash
# From source
git clone https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git
cd hjLabs.in-google-ads-mcp
pip install -e .

# Or directly via pip from GitHub
pip install git+https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git

# Run the server
python -m ads_mcp.server
```

---

## Authentication

You need a [Google Ads Developer Token](https://developers.google.com/google-ads/api/docs/get-started/dev-token) for all authentication methods. Record it — you'll use it in every config.

### Option 1: OAuth Refresh Token (Recommended)

Best for personal accounts and production use. Run the included helper script:

```bash
chmod +x get_refresh_token.sh
./get_refresh_token.sh
```

Then set these environment variables:

```bash
export GOOGLE_ADS_DEVELOPER_TOKEN="your_developer_token"
export GOOGLE_ADS_REFRESH_TOKEN="your_refresh_token"
export GOOGLE_ADS_CLIENT_ID="your_oauth_client_id"
export GOOGLE_ADS_CLIENT_SECRET="your_oauth_client_secret"
```

To create an OAuth 2.0 client:
1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create an OAuth 2.0 Client ID (Desktop app type)
3. Enable the [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com) in your project
4. Authorize the scope: `https://www.googleapis.com/auth/adwords`

### Option 2: Application Default Credentials (ADC)

Best for Google Cloud environments and service accounts.

```bash
# Using an OAuth desktop client
gcloud auth application-default login \
  --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
  --client-id-file=YOUR_CLIENT_JSON_FILE

# Using service account impersonation
gcloud auth application-default login \
  --impersonate-service-account=SERVICE_ACCOUNT_EMAIL \
  --scopes=https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform
```

Set:
```bash
export GOOGLE_ADS_DEVELOPER_TOKEN="your_developer_token"
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"
```

### Option 3: google-ads.yaml (Python Client Library)

If you already have a working `google-ads.yaml` from the Google Ads Python client library, you can reuse it. See the [official setup guide](https://developers.google.com/google-ads/api/docs/client-libs/python/).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | ✅ Always | Your Google Ads developer token |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth only | OAuth refresh token for the Google Ads account |
| `GOOGLE_ADS_CLIENT_ID` | OAuth only | OAuth 2.0 client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth only | OAuth 2.0 client secret |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC only | Path to service account or ADC credentials JSON |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC only | Manager account (MCC) customer ID |
| `GOOGLE_CLOUD_PROJECT` | Optional | Google Cloud project ID |

---

## Manager Account (MCC) Support

If your Google Ads account is managed through a Manager Account (MCC), add the manager's customer ID:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "python",
      "args": ["-m", "ads_mcp.server"],
      "cwd": "/path/to/hjLabs.in-google-ads-mcp",
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
        "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
        "GOOGLE_ADS_CLIENT_ID": "YOUR_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET": "YOUR_CLIENT_SECRET",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "YOUR_MANAGER_CUSTOMER_ID"
      }
    }
  }
}
```

See [Google Ads MCC documentation](https://developers.google.com/google-ads/api/docs/concepts/call-structure#cid) for details.

---

## Sample Prompts

Once connected, try these:

### Account Overview
```
What campaigns do I have for customer 4170793536?
How much have I spent this month across all campaigns?
What is my current billing balance and how much budget remains?
```

### Performance Analysis
```
Show me keyword performance for the last 30 days.
Which keywords have a quality score below 5?
Break down my campaign performance by device.
Which hours of the day are my ads performing best?
Who are my top competitors in auction insights?
What is my search impression share and how much am I losing to budget vs. rank?
```

### Keyword Research & Mining
```
Find keyword ideas for "machine learning consulting" targeting India.
What are the top 20 search terms that triggered my ads last month?
Add the search terms with more than 3 clicks as exact-match keywords.
```

### Campaign Optimization
```
Switch my campaign to Maximize Conversions bidding.
Set a Target CPA of 500 INR for my main campaign.
Pause all keywords with 0 conversions and more than 200 INR spent.
Add these negative keywords at campaign level: free, tutorial, course, DIY.
What recommendations does Google have for my account? Apply the budget ones.
```

### Ad & Asset Management
```
Create a sitelink "Free AI Consultation" pointing to https://hjlabs.in/contact.
Link it to my campaign.
Set my ad schedule to Monday–Friday 9am–9pm and Saturday 10am–6pm.
Show me approval status for all ads in campaign 23711872931.
```

### Raw GAQL
```
Run this GAQL: SELECT campaign.name, metrics.clicks, metrics.cost_micros
FROM campaign WHERE segments.date DURING LAST_30_DAYS ORDER BY metrics.cost_micros DESC
```

---

## Architecture

```
hjLabs.in-google-ads-mcp/
├── ads_mcp/
│   ├── server.py                  # MCP server entry point
│   ├── coordinator.py             # MCP instance registration
│   ├── utils.py                   # Google Ads client, auth, proto serialization
│   ├── mcp_header_interceptor.py  # Adds usage tracking header to API calls
│   ├── tools/
│   │   ├── campaigns.py           # Campaigns, budgets, ad groups, ads, keywords, scheduling
│   │   ├── assets.py              # Asset creation (sitelinks, callouts, images, video, etc.)
│   │   ├── asset_links.py         # Asset linking to campaigns / ad groups / accounts
│   │   ├── billing.py             # Billing info, account spend, daily spend trend
│   │   ├── analytics.py           # Device, geo, hourly performance; quality scores; auction insights
│   │   ├── bidding.py             # Bidding strategy management (Target CPA, Maximize Conversions, etc.)
│   │   ├── keyword_planning.py    # Keyword Planner API (ideas + forecasts)
│   │   ├── recommendations.py     # List, apply, and dismiss Google Ads recommendations
│   │   ├── search.py              # Raw GAQL search
│   │   ├── core.py                # list_accessible_customers
│   │   └── get_resource_metadata.py
│   └── resources/
│       ├── discovery.py
│       ├── metrics.py
│       ├── segments.py
│       └── release_notes.py
├── get_refresh_token.sh           # Helper to get OAuth refresh token
├── pyproject.toml
└── README.md
```

### Key Design Decisions

- **Lazy client initialization** — The Google Ads client is initialized on first use so the server starts cleanly even if credentials aren't configured yet.
- **Full proto serialization** — All proto types (`proto.Enum`, `proto.Message`, `RepeatedComposite`, `RepeatedScalar`) are handled in `format_output_value` — no serialization crashes.
- **Per-request MCC support** — Each tool accepts an optional `login_customer_id` parameter for MCC scenarios.
- **OAuth + ADC fallback** — Automatically uses OAuth refresh token if env vars are set, falls back to Application Default Credentials otherwise.

---

## Prerequisites

- Python 3.10 or higher
- A Google Ads account with API access
- A [Google Ads Developer Token](https://developers.google.com/google-ads/api/docs/get-started/dev-token) (Basic Access is sufficient for testing)
- OAuth 2.0 credentials or Application Default Credentials

### Getting a Developer Token

1. Sign in to your [Google Ads manager account](https://ads.google.com/)
2. Go to **Tools → API Center**
3. Apply for a developer token
4. Basic Access is sufficient for testing; Standard Access is needed for production

---

## Notes

1. This server exposes your Google Ads data to the AI agent you connect it to. Only connect to agents you trust.
2. An extra usage header is added to API calls to help track MCP server adoption.
3. For technical issues, please [open a GitHub issue](https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp/issues).

---

## Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) before submitting a pull request.

Areas where contributions are especially appreciated:
- New tool implementations (Performance Max, Smart Campaigns, Display Network)
- Additional bidding strategy support
- Better error messages and input validation
- Test coverage

---

## Related Projects

- [googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp) — Official upstream Google MCP server (read-only, 2 tools)
- [hjLabs.in](https://hjlabs.in) — Industrial automation and AI/ML consulting

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ by [Hemang Joshi](https://github.com/hemangjoshi37a) | [hjLabs.in](https://hjlabs.in)*  
*Give Claude full autonomous control of your Google Ads. Star ⭐ if this saves you time.*
