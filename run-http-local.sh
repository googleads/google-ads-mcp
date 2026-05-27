#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.env.docker"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"

DEFAULT_ADC_PATH="/Users/varunbhayana/Desktop/projects/google-ads-mcp/.gcloud/application_default_credentials.json"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Missing ${VENV_PYTHON}"
  echo "Create the virtualenv and install dependencies first."
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-${DEFAULT_ADC_PATH}}"
export MCP_LOCAL_HTTP="${MCP_LOCAL_HTTP:-true}"
export PORT="${PORT:-8080}"

if [[ ! -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  echo "ADC file not found: ${GOOGLE_APPLICATION_CREDENTIALS}"
  exit 1
fi

echo "Starting Google Ads MCP on http://127.0.0.1:${PORT}/mcp"
echo "Using env file: ${ENV_FILE}"
echo "Using ADC file: ${GOOGLE_APPLICATION_CREDENTIALS}"

exec "${VENV_PYTHON}" -m ads_mcp.server
