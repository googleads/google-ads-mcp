# Local Development Setup

This guide documents the exact local setup to run this repository from source on macOS with `zsh`.

## What Lives in This Repo (Not Committed)

| File / Dir | Purpose |
|---|---|
| `.venv/` | Local Python virtual environment |
| `.env.local` | Local credentials and runtime env vars |
| `.env.local.example` | Template — copy this to `.env.local` |
| `run-local.sh` | Starts the MCP server using values from `.env.local` |
| `gcloud-local.sh` | Runs `gcloud` with a repo-local config directory |
| `.gcloud/` | Repo-local Google Cloud CLI config and ADC credentials |
| `.mcp.json` | Claude Code MCP client config (not committed — contains local paths) |

---

## Prerequisites

- macOS with Homebrew
- Python 3.11 (`brew install python@3.11`)
- Google Cloud CLI (`brew install --cask google-cloud-sdk`)
- A Google Ads developer token
- A Google Cloud project with the Google Ads API enabled
- OAuth client credentials JSON (for ADC login)

---

## Step 1 — Create the Virtual Environment

From the repo root:

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
```

Then install the project into that environment:

```bash
./.venv/bin/pip install -e .
```

This installs the local entrypoint used by the repo:

```bash
./.venv/bin/python -c "import ads_mcp.server; print('ok')"
```

---

## Step 2 — Authenticate with Application Default Credentials

Use the local `gcloud` wrapper so credentials stay inside `.gcloud/` instead of your global `~/.config/gcloud`:

```bash
./gcloud-local.sh auth application-default login \
  --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
  --client-id-file /absolute/path/to/your-oauth-client.json
```

When complete, the credentials file is at:

```
.gcloud/application_default_credentials.json
```

---

## Step 3 — Configure `.env.local`

Copy the template:

```bash
cp .env.local.example .env.local
```

Fill in `.env.local`:

```env
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_ADS_DEVELOPER_TOKEN=your-developer-token
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/repo/.gcloud/application_default_credentials.json

# Required if your accounts are under an MCC (manager account).
# Set this to the top-level MCC ID, digits only, no hyphens.
# All data queries must still target a leaf client account ID — see Account Structure below.
GOOGLE_ADS_LOGIN_CUSTOMER_ID=5061122756
```

---

## Step 4 — Start the Server

```bash
./run-local.sh
```

This loads `.env.local` and starts `.venv/bin/google-ads-mcp`. The process listens for MCP messages over stdio. It will appear to hang — that is normal. The server is waiting for a client to connect.

---

## Step 5 — Configure Claude Code (`.mcp.json`)

Create `.mcp.json` at the repo root. This file is gitignored because it contains absolute local paths.

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "/absolute/path/to/repo/.venv/bin/google-ads-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/repo/.gcloud/application_default_credentials.json",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your-developer-token",
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "5061122756"
      }
    }
  }
}
```

Replace `/absolute/path/to/repo` with the actual path on your machine.

After creating this file, restart Claude Code. The MCP server starts automatically when Claude Code loads the project.

---

## Account Structure

The credential authenticates as a top-level MCC. Queries must target a **leaf client account** (a non-manager account inside the MCC):

- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` = the top-level MCC ID (e.g. `5061122756`)
- `customer_id` passed to each tool = a leaf account ID (e.g. `1673268103`)
- IDs must be digits only — remove any hyphens

To list all leaf accounts under the MCC, use the `search` tool with:

```
resource: customer_client
fields: [
  "customer_client.client_customer",
  "customer_client.descriptive_name",
  "customer_client.level",
  "customer_client.manager",
  "customer_client.status"
]
customer_id: 5061122756
conditions: ["customer_client.level <= 2"]
```

Filter for rows where `customer_client.manager = false` — those are the queryable leaf accounts.

---

## Available MCP Tools

### Built-in (generic)

| Tool | Description |
|---|---|
| `list_accessible_customers` | Returns top-level MCC IDs accessible by the credential |
| `get_resource_metadata` | Returns selectable/filterable/sortable fields for any GAQL resource |
| `search` | Runs any GAQL query against a valid resource |

### Custom (curated)

| Tool | Description |
|---|---|
| `get_search_term_report` | Search terms that triggered ads — for negative keyword discovery. Inputs: `customer_id`, `start_date`, `end_date`, optional `campaign_id`, `ad_group_id`, `min_impressions`, `limit`. |

---

## Example: Run `get_search_term_report`

```python
get_search_term_report(
    customer_id="1635583349",   # Stage_Haryanavi_2025 — digits only, no hyphens
    start_date="2026-01-01",
    end_date="2026-05-06",
    min_impressions=10,
    limit=200,
)
```

Returns rows with: `search_term`, `status` (ADDED / EXCLUDED / NONE), `triggering_keyword`, `match_type`, `impressions`, `clicks`, `ctr`, `cost_micros`, `conversions`, `top_impression_pct`, `abs_top_impression_pct`.

`status = NONE` means the term is not yet added as a keyword or negative — these are the candidates to review for negative keyword additions.

---

## Troubleshooting

**`Missing .env.local`**

```bash
cp .env.local.example .env.local
```

**`GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set`**

Fill in `GOOGLE_ADS_DEVELOPER_TOKEN` in `.env.local`.

**`google-ads-mcp: command not found`**

```bash
./.venv/bin/pip install -e .
```

**`Metrics cannot be requested for a manager account`**

You passed an MCC ID as `customer_id`. Use a leaf (non-manager) client account ID instead. See Account Structure above.

**`User doesn't have permission to access customer`**

The `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is set but the account you are querying is not under that MCC, or the MCC header is missing. Verify the hierarchy using `customer_client`.

**`The developer token is only approved for use with test accounts`**

Your token does not have production access. See the Google Ads access levels documentation.

**ADC or auth errors**

Re-run the login flow:

```bash
./gcloud-local.sh auth application-default login \
  --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
  --client-id-file /absolute/path/to/your-oauth-client.json
```

---

## Security Notes

- Do not commit `.env.local` — it contains real credentials
- Do not commit `.gcloud/` — it contains ADC tokens
- Do not commit `.mcp.json` — it contains absolute local paths and tokens
- If credentials were accidentally exposed, rotate them immediately in Google Cloud IAM
