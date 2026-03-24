# Setup Guide: Google Ads MCP Server (Full)

Complete step-by-step guide to set up the Google Ads MCP server with read + write capabilities.

## Prerequisites

You need three things from Google:

| Credential | What it is | Where to get it |
|---|---|---|
| **Developer Token** | 22-character string for API access | [Google Ads API Center](https://ads.google.com/aw/apicenter) |
| **Project ID** | Your Google Cloud project identifier | [Google Cloud Console](https://console.cloud.google.com) |
| **Credentials File** | OAuth 2.0 authorized user credentials | Generated via `gcloud` (see below) |

## Step 1: Get your Developer Token

1. Sign in to [Google Ads](https://ads.google.com)
2. Go to **Tools & Settings** (wrench icon) → **API Center**
3. If you don't have a developer token, apply for one
4. Copy the token (looks like `aBcDeFgHiJkLmNoPqRsT12`)

## Step 2: Set up Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project or select an existing one
3. Note the **Project ID** (e.g., `my-ads-project-123456`)
4. Enable the Google Ads API:
   ```bash
   gcloud services enable googleads.googleapis.com --project=YOUR_PROJECT_ID
   ```
   Or manually: **APIs & Services** → **Library** → search "Google Ads API" → **Enable**

## Step 3: Generate Credentials File

### Install gcloud CLI (if not installed)

**macOS (Homebrew):**
```bash
brew install google-cloud-sdk
```

**macOS/Linux (direct):**
```bash
curl https://sdk.cloud.google.com | bash
```

Restart your terminal after installation.

### Authenticate with Google Ads scopes

This is the critical step — you must include the `adwords` scope:

```bash
gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/adwords"
```

This opens your browser. Sign in with the Google account that has access to your Google Ads accounts.

### Set the quota project

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

This saves credentials to:
```
~/.config/gcloud/application_default_credentials.json
```

> **Important:** If you re-run the login command later, you must also re-run the quota project command — the login resets it.

## Step 4: Install pipx

```bash
# macOS
brew install pipx
pipx ensurepath

# Linux
python3 -m pip install --user pipx
pipx ensurepath
```

Restart your terminal after installation.

## Step 5: Configure the MCP Server

### For Claude Desktop

Open Claude Desktop → **Settings** → **Developer** → **Edit Config**

This opens `claude_desktop_config.json`. Add the following:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": [
        "run",
        "--spec",
        "git+https://github.com/SaiSatya16/google-ads-mcp-full.git",
        "google-ads-mcp"
      ],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/.config/gcloud/application_default_credentials.json",
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
      }
    }
  }
}
```

### For Claude Code CLI

Add to your Claude Code MCP settings (`~/.claude/settings.json` or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": [
        "run",
        "--spec",
        "git+https://github.com/SaiSatya16/google-ads-mcp-full.git",
        "google-ads-mcp"
      ],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/.config/gcloud/application_default_credentials.json",
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
      }
    }
  }
}
```

### For local development (run from source)

Clone the repo and point to the local path:

```bash
git clone https://github.com/SaiSatya16/google-ads-mcp-full.git
```

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "pipx",
      "args": [
        "run",
        "--spec",
        "/path/to/google-ads-mcp-full",
        "google-ads-mcp"
      ],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/.config/gcloud/application_default_credentials.json",
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
      }
    }
  }
}
```

> **Tip:** When developing locally, clear the pipx cache after code changes:
> ```bash
> rm -rf ~/.local/pipx/.cache
> ```
> Then restart your MCP client.

## Step 6: Manager Account Setup (Optional)

If you access Google Ads through a **Manager Account** (MCC), add the manager account ID:

```json
"env": {
  "GOOGLE_APPLICATION_CREDENTIALS": "...",
  "GOOGLE_PROJECT_ID": "...",
  "GOOGLE_ADS_DEVELOPER_TOKEN": "...",
  "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "1234567890"
}
```

The `login_customer_id` should be the **Manager Account ID** (numbers only, no hyphens).

You can also pass `login_customer_id` as a parameter on any tool call to switch between manager accounts without restarting.

## Step 7: Verify the Setup

Restart your MCP client (Claude Desktop or Claude Code), then try:

```
What customers do I have access to?
```

This calls `list_accessible_customers` and should return your Google Ads account IDs.

Then try:

```
How many active campaigns do I have?
```

This uses `search` and `get_resource_metadata` to query your campaigns.

## Troubleshooting

### "Your default credentials were not found"
You haven't run `gcloud auth application-default login` yet, or the path in your config is wrong. Verify the file exists:
```bash
cat ~/.config/gcloud/application_default_credentials.json
```

### "Request had invalid authentication credentials"
Your credentials file is the raw OAuth client secret (downloaded from Cloud Console) instead of the authorized user credentials. Run `gcloud auth application-default login` to generate the correct file.

### "Google Ads API has not been used in project 764086051850"
The quota project isn't set. Run:
```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

### "PERMISSION_DENIED" or "The caller does not have permission"
The OAuth scopes don't include Google Ads. Re-authenticate with:
```bash
gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/adwords"
```
Then re-run the quota project command.

### "OPERATION_NOT_PERMITTED_FOR_CONTEXT"
You're trying to create a campaign on a Manager Account. Campaigns must be created on client accounts. Add `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to your env config, or pass `login_customer_id` as a tool parameter.

### Code changes not taking effect
pipx caches installed packages. Clear the cache:
```bash
rm -rf ~/.local/pipx/.cache
```
Then restart your MCP client.

### Server not starting (no tools visible)
Check for Python errors by running the server manually:
```bash
pipx run --spec /path/to/google-ads-mcp-full google-ads-mcp
```

## Available Tools (32)

### Read Tools (3)
| Tool | Description |
|---|---|
| `list_accessible_customers` | List all Google Ads accounts you have access to |
| `search` | Query Google Ads data using GAQL |
| `get_resource_metadata` | Get selectable/filterable/sortable fields for any resource |

### Campaign Management (4)
| Tool | Description |
|---|---|
| `create_campaign` | Create Search/Display/Shopping campaigns |
| `create_performance_max_campaign` | Create PMax campaigns with brand assets |
| `update_campaign` | Update campaign name, status, budget, dates |
| `set_campaign_status` | Quick enable/pause toggle |

### Ad Group Management (2)
| Tool | Description |
|---|---|
| `create_ad_group` | Create ad groups with CPC bids |
| `update_ad_group` | Update ad group name, status, bids |

### Ads & Keywords (6)
| Tool | Description |
|---|---|
| `create_responsive_search_ad` | Create RSAs with headlines and descriptions |
| `add_keywords` | Add keywords with match types |
| `update_ad_status` | Enable, pause, or remove ads |
| `update_keyword` | Update keyword status or bid |
| `remove_ad` | Permanently remove ads (with confirmation) |
| `remove_keyword` | Permanently remove keywords (with confirmation) |

### Asset Creation (10)
| Tool | Description |
|---|---|
| `create_text_asset` | Text assets for PMax |
| `create_image_asset` | Upload images from URL or local file |
| `create_youtube_video_asset` | YouTube video assets |
| `create_sitelink_asset` | Sitelink extensions |
| `create_callout_asset` | Callout extensions |
| `create_structured_snippet_asset` | Structured snippet extensions |
| `create_call_asset` | Call extensions |
| `create_promotion_asset` | Promotion extensions |
| `create_price_asset` | Price listing extensions |
| `create_lead_form_asset` | Lead generation forms |

### Asset Linking (4)
| Tool | Description |
|---|---|
| `link_asset_to_campaign` | Attach assets to campaigns |
| `link_asset_to_ad_group` | Attach assets to ad groups |
| `link_assets_to_customer` | Attach assets at account level |
| `remove_campaign_asset` | Remove asset links (with confirmation) |

### Asset Groups / Performance Max (3)
| Tool | Description |
|---|---|
| `create_asset_group` | Create asset groups with batch mutate |
| `add_assets_to_asset_group` | Add assets to existing groups |
| `remove_asset_from_asset_group` | Remove assets (with confirmation) |

## Sample Prompts

**Account overview:**
```
What customers do I have access to?
```

**Campaign analysis:**
```
Show me all active campaigns with their performance this week
```

**Create a campaign:**
```
Create a paused Search campaign called "Spring Sale" with $10/day budget
```

**Full PMax setup:**
```
Create a Performance Max campaign for my business with headlines,
descriptions, images, and sitelinks
```

**Manage keywords:**
```
Add these keywords to my campaign: "running shoes", "best sneakers", "athletic footwear"
```

**Add extensions:**
```
Create a sitelink for "Free Shipping" pointing to /shipping and link it to my campaign
```
