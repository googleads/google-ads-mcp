<div align="center">

# 🤖 Google Ads MCP Server

### Give Claude AI Full Autonomous Control Over Your Google Ads Account

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Google Ads API](https://img.shields.io/badge/Google_Ads_API-v23-4285F4?style=for-the-badge&logo=googleads&logoColor=white)](https://developers.google.com/google-ads/api/reference/rpc/v23/overview)
[![MCP Protocol](https://img.shields.io/badge/MCP-Protocol-FF6B35?style=for-the-badge)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/github/license/hemangjoshi37a/hjLabs.in-google-ads-mcp?style=for-the-badge)](LICENSE)
[![Stars](https://img.shields.io/github/stars/hemangjoshi37a/hjLabs.in-google-ads-mcp?style=for-the-badge&color=yellow)](https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp/stargazers)

<br/>

**A Model Context Protocol (MCP) server that connects AI assistants directly to the Google Ads API — enabling autonomous campaign management, bidding optimization, keyword research, and performance analysis through natural language.**

*Create campaigns, switch bidding strategies, mine search terms, check account balance, and apply Google's recommendations — all by chatting with Claude.*

<br/>

[Getting Started](#-getting-started) · [Features](#-features) · [Tools](#-mcp-tools-65) · [Configuration](#-configuration) · [Sample Prompts](#-sample-prompts) · [Contributing](#-contributing) · [Contact](#-contact)

<br/>

---

</div>

## 🎯 What is this?

Google Ads MCP Server is a **Model Context Protocol (MCP)** server that gives AI assistants direct access to your **Google Ads** account. It exposes **65+ tools** that let AI assistants like **Claude**, **Gemini CLI**, **Gemini Code Assist**, and **GitHub Copilot**:

- 🎯 **Create and manage** campaigns, ad groups, ads, keywords, and budgets
- 💰 **Switch bidding strategies** — Target CPA, Maximize Conversions, Target ROAS, Manual CPC
- 💡 **Research keywords** using the Google Keyword Planner API directly from chat
- 📊 **Analyze performance** by device, geo, hour of day, and keyword quality score
- 🏆 **See auction insights** — which competitors are overlapping your impressions
- 🔗 **Manage assets** — sitelinks, callouts, structured snippets, call assets, images, lead forms
- 📋 **Apply Google's recommendations** without touching the dashboard
- 🧾 **Check account balance** and daily spend trends on demand

> **Think of it as giving Claude the ability to be your Google Ads account manager — pulling data, spotting inefficiencies, and executing optimizations autonomously.**

<br/>

## ✨ Features

<table>
<tr>
<td width="50%">

### 📊 Performance Analytics
- Campaign, ad group, keyword, and ad-level metrics
- Device breakdown (Mobile / Desktop / Tablet)
- Geographic performance by city and country
- Hour × day-of-week performance heatmap
- Search impression share (lost to budget vs. rank)
- Auction insights: competitor overlap and outranking share

</td>
<td width="50%">

### 💰 Smart Bidding Control
- Switch to Target CPA in a single tool call
- Maximize Conversions with optional CPA constraint
- Target ROAS / Maximize Conversion Value
- Target Impression Share (Anywhere / Top / Abs Top)
- Revert to Manual CPC with Enhanced CPC toggle
- Bulk keyword bid updates in one API call

</td>
</tr>
<tr>
<td>

### 🔑 Keyword Management
- Add keywords with any match type (Exact, Phrase, Broad)
- Campaign-level and ad-group-level negatives
- Mine search terms report → add directly as keywords
- Quality Score per keyword (Expected CTR, Ad Relevance, Landing Page)
- Keyword Planner: search volume, competition, bid range
- Traffic/spend forecast before committing budget

</td>
<td>

### 🔗 Asset Management
- Sitelinks, callouts, structured snippets
- Call assets with conversion reporting
- Image assets from URL or local file
- Promotion, price, and lead form assets
- YouTube video assets
- Link assets to campaigns, ad groups, or entire account

</td>
</tr>
<tr>
<td>

### 🧾 Billing & Budget
- Current billing setup and payment method
- Approved budget, amount served, estimated remaining
- Day-by-day spend burn rate for last N days
- Per-campaign spend summary for any date range

</td>
<td>

### 📋 Recommendations & Automation
- List all pending Google Ads automated recommendations
- Apply recommendations by resource name
- Dismiss irrelevant recommendations
- Raw GAQL query support for any custom report

</td>
</tr>
</table>

<br/>

## 🛠️ MCP Tools (65+)

<details>
<summary><b>🧾 Billing & Account Spend (3 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `get_billing_info` | Billing setup, payment method, approved budget, amount served, estimated remaining balance |
| `get_account_spend_summary` | Total spend/clicks/conversions across all campaigns for any date range |
| `get_daily_spend_trend` | Day-by-day burn rate for the last N days |

</details>

<details>
<summary><b>📊 Advanced Analytics (6 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `get_device_performance` | Performance by device: MOBILE, DESKTOP, TABLET — essential for bid adjustments |
| `get_geo_performance` | Clicks, spend, conversions by geographic location |
| `get_hourly_performance` | Hour × day-of-week heatmap to identify peak hours |
| `get_quality_scores` | Quality Score (1-10), Expected CTR, Ad Relevance, Landing Page Experience per keyword |
| `get_auction_insights` | Competitor domains, impression share overlap, outranking share |
| `get_search_impression_share` | Lost IS due to budget vs. rank; top and abs-top impression share |

</details>

<details>
<summary><b>💰 Bidding Strategies (6 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `set_target_cpa` | Switch campaign to Target CPA smart bidding |
| `set_maximize_conversions` | Maximize conversions within budget (optional Target CPA constraint) |
| `set_maximize_conversion_value` | Maximize conversion value / ROAS (optional Target ROAS) |
| `set_manual_cpc` | Revert to Manual CPC with optional Enhanced CPC |
| `set_target_impression_share` | Visibility-based bidding: ANYWHERE, TOP_OF_PAGE, ABS_TOP_OF_PAGE |
| `update_keyword_bids_bulk` | Update CPC bids for multiple keywords in a single API call |

</details>

<details>
<summary><b>💡 Keyword Planning & Research (2 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `get_keyword_ideas` | Search volume, competition, and top-of-page bid range for seed keywords via Keyword Planner |
| `get_keyword_forecast` | Traffic/spend/conversion forecast for a keyword set at a given budget and bid |

</details>

<details>
<summary><b>📋 Recommendations (3 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `list_recommendations` | All pending Google Ads automated recommendations with estimated impact deltas |
| `apply_recommendation` | Apply a specific recommendation by resource name |
| `dismiss_recommendation` | Dismiss one or more irrelevant recommendations |

</details>

<details>
<summary><b>🎯 Campaign Management (7 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `create_campaign_budget` | Create a shared daily budget |
| `update_campaign_budget` | Change a campaign's daily budget amount |
| `create_search_campaign` | Create a Search campaign with Target Spend bidding |
| `update_campaign_status` | Enable or pause a campaign |
| `remove_campaign` | Permanently remove a campaign |
| `list_campaigns` | List all campaigns with status, budget, and resource names |
| `get_campaign_performance` | Clicks, impressions, cost, and conversions per campaign |

</details>

<details>
<summary><b>📍 Geo Targeting (2 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `suggest_geo_targets` | Look up geo target constant IDs by location name and country code |
| `add_geo_targets` | Add location targets to a campaign |

</details>

<details>
<summary><b>🗂 Ad Groups (7 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `create_ad_group` | Create an ad group with CPC bid |
| `update_ad_group` | Rename an ad group |
| `update_ad_group_status` | Enable or pause an ad group |
| `update_ad_group_bid` | Update default CPC bid for an ad group |
| `set_ad_schedule` | Set dayparting schedules (replaces existing schedule atomically) |
| `list_ad_groups` | List all ad groups in a campaign |
| `get_ad_group_performance` | Per-ad-group performance breakdown |

</details>

<details>
<summary><b>🔑 Keywords (10 tools)</b></summary>

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

</details>

<details>
<summary><b>📝 Ads — Responsive Search Ads (4 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `create_responsive_search_ad` | Create RSA with headlines, descriptions, and display URL paths (path1/path2) |
| `list_ads` | List ads with approval status and ad strength |
| `update_ad_status` | Enable, pause, or remove a specific ad |
| `get_ad_performance` | Per-ad metrics with ad strength and approval status |

</details>

<details>
<summary><b>🔗 Assets & Asset Linking (14 tools)</b></summary>

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

</details>

<details>
<summary><b>🔄 Conversions & Discovery (4 tools)</b></summary>

| Tool | Description |
|------|-------------|
| `create_conversion_action` | Create a webpage conversion action |
| `list_conversion_actions` | List all conversion actions with tag snippet details |
| `search` | Run any GAQL query against the Google Ads API directly |
| `list_accessible_customers` | List all customer accounts accessible to the authenticated user |

</details>

<br/>

## 🚀 Getting Started

### Prerequisites

| Requirement | Details |
|------------|---------|
| **Python** | 3.10 or newer |
| **Google Ads Account** | With API access enabled |
| **Developer Token** | [Apply here](https://developers.google.com/google-ads/api/docs/get-started/dev-token) — Basic Access sufficient for testing |
| **AI Client** | Claude Desktop, Claude Code, Gemini CLI, or any MCP-compatible agent |

### 1. Get a Developer Token

1. Sign in to your [Google Ads manager account](https://ads.google.com/)
2. Go to **Tools → API Center**
3. Apply for a developer token (Basic Access is sufficient for testing)

### 2. Set Up OAuth Credentials

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create an OAuth 2.0 Client ID (Desktop app type)
3. Enable the [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com) in your project
4. Run the helper script to get your refresh token:

```bash
git clone https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git
cd hjLabs.in-google-ads-mcp
chmod +x get_refresh_token.sh
./get_refresh_token.sh
```

### 3. Install

```bash
# From source
pip install -e .

# Or directly via pip
pip install git+https://github.com/hemangjoshi37a/hjLabs.in-google-ads-mcp.git
```

<br/>

## ⚙️ Configuration

### Claude Desktop / Claude Code

Edit your Claude Desktop config:
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

Or run directly from GitHub using `pipx` (no local clone needed):

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

### Gemini CLI / Code Assist

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

### Manager Account (MCC)

If your account is accessed via a Manager Account (MCC), add the manager's customer ID:

```json
"env": {
  "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
  "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
  "GOOGLE_ADS_CLIENT_ID": "YOUR_CLIENT_ID",
  "GOOGLE_ADS_CLIENT_SECRET": "YOUR_CLIENT_SECRET",
  "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "YOUR_MANAGER_CUSTOMER_ID"
}
```

### Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | ✅ Always | Your Google Ads developer token |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth only | OAuth refresh token |
| `GOOGLE_ADS_CLIENT_ID` | OAuth only | OAuth 2.0 client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth only | OAuth 2.0 client secret |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC only | Path to service account / ADC credentials JSON |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC only | Manager account customer ID |
| `GOOGLE_CLOUD_PROJECT` | Optional | Google Cloud project ID |

<br/>

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AI Assistant                         │
│        (Claude / Gemini / Copilot / Cursor)             │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Protocol (stdio/JSON-RPC)
┌──────────────────────▼──────────────────────────────────┐
│            Google Ads MCP Server (65+ Tools)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ Billing  │ │Analytics │ │ Bidding  │ │  Keyword  │ │
│  │  (3)     │ │   (6)    │ │   (6)   │ │ Planning  │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │Campaigns │ │Keywords  │ │  Assets  │ │  Recs     │ │
│  │  (7)     │ │  (10)    │ │  (14)    │ │   (3)     │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │ Google Ads Python API v23
┌──────────────────────▼──────────────────────────────────┐
│                 Google Ads API                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │Campaigns │ │ Keywords │ │  Assets  │ │ Reporting │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Lazy client initialization** — server starts cleanly even without credentials set
- **Full proto serialization** — `RepeatedComposite`, `RepeatedScalar`, `proto.Message` all handled
- **OAuth + ADC fallback** — uses OAuth refresh token if env vars set, else falls back to ADC
- **Per-request MCC support** — each tool accepts optional `login_customer_id`

<br/>

## 🔧 Sample Prompts

<table>
<tr>
<td width="33%" valign="top">

### 📊 Performance Analysis
- "What's my total spend this month and how many conversions?"
- "Which keywords have quality score below 5?"
- "Break down performance by device for the last 7 days"
- "Which hour of the day gets the most conversions?"
- "Who are my top 5 competitors in auction insights?"
- "What is my search impression share?"

</td>
<td width="33%" valign="top">

### 🎯 Campaign Optimization
- "Switch my campaign to Maximize Conversions"
- "Set a Target CPA of 500 INR for my main campaign"
- "Pause all keywords with 0 conversions and over 200 INR spent"
- "Add these as campaign-level negatives: free, tutorial, DIY"
- "What recommendations does Google have? Apply the budget ones"
- "Update bid to 120 INR for my top 5 keywords"

</td>
<td width="33%" valign="top">

### 💡 Keyword Research & Mining
- "Find keyword ideas for 'AI consulting India'"
- "What search terms triggered my ads last 30 days?"
- "Add the search terms with 3+ clicks as exact-match keywords"
- "Forecast traffic for these 10 keywords at ₹1000/day budget"
- "Create a sitelink 'Free Consultation' → hjlabs.in/contact"
- "Set my ad schedule Mon–Fri 9am–9pm, Sat 10am–6pm"

</td>
</tr>
</table>

<br/>

## 📋 Changelog

### [2.0.0] — April 2026

#### Added (20+ new tools across 5 new modules)
- **`get_billing_info`** — Account balance, payment method, approved budget and remaining
- **`get_account_spend_summary`** — Cross-campaign spend summary for any date range
- **`get_daily_spend_trend`** — Day-by-day burn rate
- **`get_device_performance`** — Mobile/desktop/tablet breakdown
- **`get_geo_performance`** — Location-level performance
- **`get_hourly_performance`** — Hour × day-of-week heatmap
- **`get_quality_scores`** — Full Quality Score details per keyword
- **`get_auction_insights`** — Competitor overlap and outranking share
- **`get_search_impression_share`** — Lost IS analysis
- **`set_target_cpa`** / **`set_maximize_conversions`** / **`set_maximize_conversion_value`** — Smart bidding
- **`set_manual_cpc`** / **`set_target_impression_share`** — Manual and visibility bidding
- **`update_keyword_bids_bulk`** — Batch bid updates
- **`get_keyword_ideas`** — Keyword Planner integration
- **`get_keyword_forecast`** — Traffic forecasting
- **`list_recommendations`** / **`apply_recommendation`** / **`dismiss_recommendation`** — Recommendations management
- **`add_search_terms_as_keywords`** — Search term mining workflow

### [1.0.0] — March 2026

#### Added (43 tools)
- Full campaign, ad group, ad, keyword management
- RSA creation with path1/path2 display URL paths
- 10 asset creation tools (sitelinks, callouts, images, video, lead forms, etc.)
- 4 asset linking tools (campaign, ad group, account level)
- OAuth refresh token authentication + ADC fallback
- MCC/manager account support via `login_customer_id`
- `RepeatedComposite` proto serialization fix (prevented search tool crash)

<br/>

## 🤝 Contributing

Found a bug or have an idea? Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) before submitting a pull request.

Areas where contributions are especially appreciated:
- New tool implementations (Performance Max, Smart Campaigns, Display Network)
- Additional bidding strategy support
- Better error messages and input validation
- Test coverage

<br/>

## 📄 License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.

<br/>

---

<div align="center">

## 📬 Contact

**Hemang Joshi** — Founder, [hjLabs.in](https://hjlabs.in)

[![Email](https://img.shields.io/badge/Email-hemangjoshi37a@gmail.com-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:hemangjoshi37a@gmail.com)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Hemang_Joshi-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/hemang-joshi-046746aa)
[![YouTube](https://img.shields.io/badge/YouTube-@HemangJoshi-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/@HemangJoshi)
[![WhatsApp](https://img.shields.io/badge/WhatsApp-+91_7016525813-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)](https://wa.me/917016525813)
[![Telegram](https://img.shields.io/badge/Telegram-@hjlabs-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/hjlabs)

<br/>

**hjLabs.in** — Industrial Automation | AI/ML | IoT | Google Ads AI Tools

Serving **15+ countries** with a **4.9⭐ Google rating**

[![Website](https://img.shields.io/badge/🌐_hjLabs.in-Visit_Website-4f46e5?style=for-the-badge)](https://hjlabs.in)
[![GitHub](https://img.shields.io/badge/GitHub-hemangjoshi37a-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/hemangjoshi37a)
[![LinkTree](https://img.shields.io/badge/LinkTree-All_Links-39E09B?style=for-the-badge&logo=linktree&logoColor=white)](https://linktr.ee/hemangjoshi37a)

<br/>

---

<sub>Built with ❤️ by <a href="https://hjlabs.in">hjLabs.in</a> — Empowering marketers with autonomous AI-powered Google Ads management</sub>

<br/>

⭐ **If this project saves you time, please give it a star!** ⭐

</div>
