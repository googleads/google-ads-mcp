#!/usr/bin/env bash
# create-secrets.sh — Bootstrap Kubernetes Secrets for google-ads-mcp.
#
# Usage:
#   create-secrets.sh [--namespace NS] [--apply]
#
# Default mode (no --apply): prints generated YAML without applying.
# With --apply: creates/updates secrets in the cluster.
#
# Each required value is read from environment variables; if a var is
# unset or empty the script prompts interactively (silent input).

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
NAMESPACE="google-ads-mcp"
APPLY=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --namespace)
            NAMESPACE="${2:?--namespace requires a value}"
            shift 2
            ;;
        --apply)
            APPLY=true
            shift
            ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helper: read a value from env or prompt (silent)
# ---------------------------------------------------------------------------
read_secret() {
    local var_name="$1"
    local prompt_label="$2"

    # If already set in environment, use it
    if [[ -n "${!var_name:-}" ]]; then
        return 0
    fi

    # Prompt interactively (no echo)
    local value
    read -rsp "${prompt_label}: " value
    printf '\n' >&2
    # Export to the current environment so subsequent references work
    export "${var_name}=${value}"
}

# ---------------------------------------------------------------------------
# Collect required credentials
# ---------------------------------------------------------------------------
read_secret GOOGLE_ADS_DEVELOPER_TOKEN    "GOOGLE_ADS_DEVELOPER_TOKEN"
read_secret GOOGLE_ADS_MCP_OAUTH_CLIENT_ID     "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID"
read_secret GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET"

# Optional — only prompt if user has it set (blank = skip)
GOOGLE_ADS_LOGIN_CUSTOMER_ID="${GOOGLE_ADS_LOGIN_CUSTOMER_ID:-}"

# ---------------------------------------------------------------------------
# Dry-run helper: print YAML for one secret
# ---------------------------------------------------------------------------
print_secret_yaml() {
    local name="$1"
    shift
    kubectl create secret generic "$name" \
        --namespace "$NAMESPACE" \
        "$@" \
        --dry-run=client -o yaml
}

# ---------------------------------------------------------------------------
# Apply helper: create/update one secret (idempotent)
# ---------------------------------------------------------------------------
apply_secret() {
    local name="$1"
    shift
    kubectl create secret generic "$name" \
        --namespace "$NAMESPACE" \
        "$@" \
        --dry-run=client -o yaml \
        | kubectl apply -f -
    echo "  [ok] $name"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if [[ "$APPLY" == "true" ]]; then
    echo "==> Ensuring namespace '$NAMESPACE' exists"
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    echo "==> Creating / updating secrets in namespace '$NAMESPACE'"

    apply_secret google-ads-developer-token \
        --from-literal="GOOGLE_ADS_DEVELOPER_TOKEN=${GOOGLE_ADS_DEVELOPER_TOKEN}"

    apply_secret google-ads-oauth-client \
        --from-literal="GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=${GOOGLE_ADS_MCP_OAUTH_CLIENT_ID}" \
        --from-literal="GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=${GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET}"

    if [[ -n "${GOOGLE_ADS_LOGIN_CUSTOMER_ID}" ]]; then
        apply_secret google-ads-login-customer \
            --from-literal="GOOGLE_ADS_LOGIN_CUSTOMER_ID=${GOOGLE_ADS_LOGIN_CUSTOMER_ID}"
    else
        echo "  [skip] google-ads-login-customer (GOOGLE_ADS_LOGIN_CUSTOMER_ID is empty)"
    fi

    echo "==> Done. Secrets applied to namespace '$NAMESPACE'."
else
    echo "==> DRY-RUN mode (pass --apply to create/update)"
    echo "==> Namespace: $NAMESPACE"
    echo ""

    echo "--- # google-ads-developer-token"
    print_secret_yaml google-ads-developer-token \
        --from-literal="GOOGLE_ADS_DEVELOPER_TOKEN=${GOOGLE_ADS_DEVELOPER_TOKEN}"
    echo ""

    echo "--- # google-ads-oauth-client"
    print_secret_yaml google-ads-oauth-client \
        --from-literal="GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=${GOOGLE_ADS_MCP_OAUTH_CLIENT_ID}" \
        --from-literal="GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=${GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET}"
    echo ""

    if [[ -n "${GOOGLE_ADS_LOGIN_CUSTOMER_ID}" ]]; then
        echo "--- # google-ads-login-customer"
        print_secret_yaml google-ads-login-customer \
            --from-literal="GOOGLE_ADS_LOGIN_CUSTOMER_ID=${GOOGLE_ADS_LOGIN_CUSTOMER_ID}"
        echo ""
    else
        echo "# [skip] google-ads-login-customer (GOOGLE_ADS_LOGIN_CUSTOMER_ID is empty)"
    fi
fi
