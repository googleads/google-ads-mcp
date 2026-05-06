# Local Development Setup

This guide documents the exact local setup used to run this repository from source on macOS with `zsh`, including the helper scripts and gitignored files added in this workspace.

## What Was Added

- `.venv/`: local Python virtual environment
- `.env.local.example`: template for local environment variables
- `.env.local`: local env file used only on this machine
- `run-local.sh`: starts the MCP server using values from `.env.local`
- `gcloud-local.sh`: runs `gcloud` with a repo-local config directory
- `.gcloud/`: repo-local Google Cloud CLI config and ADC credentials
- `.gitignore` entries for `.env.local` and `.gcloud/`

## Why This Setup Exists

This repo requires Python `>=3.10`, but the default system Python on this machine was older. The setup below avoids changing the project code and keeps credentials out of tracked files.

The main goals were:

- use a compatible Python version
- keep dependencies isolated in a local virtualenv
- avoid storing Google auth state in the global `~/.config/gcloud`
- make startup a one-command flow

## Prerequisites

- Homebrew
- Python 3.11
- Google Cloud CLI
- A Google Cloud project with the [Google Ads API enabled](https://console.cloud.google.com/apis/library/googleads.googleapis.com)
- A Google Ads [Developer Token](https://developers.google.com/google-ads/api/docs/get-started/dev-token)
- An OAuth client JSON for Application Default Credentials, if you are using the ADC flow from the repo README

## Step 1: Install Python 3.11

Python 3.11 was installed with Homebrew:

```bash
brew install python@3.11
```

The installed interpreter path is:

```bash
/opt/homebrew/bin/python3.11
```

## Step 2: Create a Local Virtual Environment

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
./.venv/bin/google-ads-mcp
```

## Step 3: Verify the Local Install

Two lightweight checks were used:

```bash
./.venv/bin/python -c "import ads_mcp.server; print('server import ok')"
./.venv/bin/python -m unittest tests.server_test
```

These confirm the package imports correctly and the basic server initialization test passes.

## Step 4: Install Google Cloud CLI

The Google Cloud CLI was installed with Homebrew:

```bash
brew install --cask google-cloud-sdk
```

The main executable path is:

```bash
/opt/homebrew/bin/gcloud
```

## Step 5: Use a Repo-Local `gcloud` Config

Instead of writing Google auth state to the global config directory, this setup uses `gcloud-local.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CLOUDSDK_PYTHON="/opt/homebrew/bin/python3.11"
export CLOUDSDK_CONFIG="${ROOT_DIR}/.gcloud"

exec /opt/homebrew/bin/gcloud "$@"
```

This does two things:

- forces `gcloud` to use Python 3.11
- stores credentials and config in `./.gcloud/`

Verify it works:

```bash
./gcloud-local.sh --version
```

## Step 6: Authenticate with Application Default Credentials

The repo README supports ADC. Use the local wrapper so credentials stay inside `.gcloud/`:

```bash
./gcloud-local.sh auth application-default login \
  --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
  --client-id-file /absolute/path/to/your-oauth-client.json
```

When this succeeds, the credentials file is typically created in the repo-local config directory. In this setup, the intended path is:

```bash
/absolute/path/to/repo/.gcloud/application_default_credentials.json
```

## Step 7: Configure Environment Variables

The repo now includes `.env.local.example`:

```env
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_ADS_DEVELOPER_TOKEN=your-google-ads-developer-token
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/application_default_credentials.json
# Optional: if you access the target account through a manager account
# GOOGLE_ADS_LOGIN_CUSTOMER_ID=1234567890
```

Copy it to `.env.local`:

```bash
cp .env.local.example .env.local
```

Then update `.env.local` with real values. In this workspace, `.env.local` was prefilled to expect the repo-local ADC file:

```env
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_ADS_DEVELOPER_TOKEN=your-google-ads-developer-token
GOOGLE_APPLICATION_CREDENTIALS=/Users/varunbhayana/Desktop/projects/google-ads-mcp/.gcloud/application_default_credentials.json
# GOOGLE_ADS_LOGIN_CUSTOMER_ID=1234567890
```

## Step 8: Start the Server

Use the helper script:

```bash
./run-local.sh
```

`run-local.sh` does the following:

- checks that `.env.local` exists
- loads env vars from `.env.local`
- starts `./.venv/bin/google-ads-mcp`

The script contents are:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.env.local"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  echo "Copy .env.local.example to .env.local and fill in your values."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

exec "${ROOT_DIR}/.venv/bin/google-ads-mcp"
```

## Optional: MCP Client Configuration

If your MCP client can launch a local command directly, point it at the local binary and pass the same env vars.

Example:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "command": "/absolute/path/to/google-ads-mcp/.venv/bin/google-ads-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/application_default_credentials.json",
        "GOOGLE_PROJECT_ID": "your-gcp-project-id",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your-developer-token"
      }
    }
  }
}
```

## Security Notes

- Do not commit `.env.local`.
- Do not commit `.gcloud/`.
- Do not paste service account keys or OAuth credentials into tracked files.
- If a private key or service account JSON was exposed in chat, logs, or a file, rotate it immediately in Google Cloud IAM.

## File Reference

| File | Purpose |
|---|---|
| `LOCAL_DEVELOPMENT.md` | This local runbook |
| `run-local.sh` | Loads `.env.local` and starts the server |
| `gcloud-local.sh` | Runs `gcloud` with repo-local config and Python 3.11 |
| `.env.local.example` | Template for required env vars |
| `.env.local` | Local credentials and config values |
| `.gcloud/` | Repo-local Google Cloud CLI config and ADC state |
| `.venv/` | Local Python virtual environment |

## Troubleshooting

**`Missing .env.local`**

Create it from the template:

```bash
cp .env.local.example .env.local
```

**`GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set`**

Fill in `GOOGLE_ADS_DEVELOPER_TOKEN` inside `.env.local`.

**`google-ads-mcp: command not found`**

Reinstall the editable package:

```bash
./.venv/bin/pip install -e .
```

**`The developer token is only approved for use with test accounts`**

Your token does not yet have the required production access level. See the [Google Ads access levels documentation](https://developers.google.com/google-ads/api/docs/access-levels).

**ADC or auth errors**

Repeat the login flow with the local wrapper:

```bash
./gcloud-local.sh auth application-default login \
  --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
  --client-id-file /absolute/path/to/your-oauth-client.json
```
