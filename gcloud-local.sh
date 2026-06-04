#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CLOUDSDK_PYTHON="/opt/homebrew/bin/python3.11"
export CLOUDSDK_CONFIG="${ROOT_DIR}/.gcloud"

exec /opt/homebrew/bin/gcloud "$@"
