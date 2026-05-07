#!/usr/bin/env bash
# uninstall.sh — Uninstall the google-ads-mcp Helm release and optionally
#               delete its Secrets and namespace.
#
# Usage:
#   uninstall.sh [--namespace NS] [--release NAME] [--force-namespace]
#
# Options:
#   --namespace       Kubernetes namespace  (default: google-ads-mcp)
#   --release         Helm release name     (default: google-ads-mcp)
#   --force-namespace Allow deletion of namespaces other than 'google-ads-mcp'

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
NAMESPACE="google-ads-mcp"
RELEASE="google-ads-mcp"
FORCE_NAMESPACE=false

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --namespace)
            NAMESPACE="${2:?--namespace requires a value}"
            shift 2
            ;;
        --release)
            RELEASE="${2:?--release requires a value}"
            shift 2
            ;;
        --force-namespace)
            FORCE_NAMESPACE=true
            shift
            ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Safety guard — prevent accidental deletion of unintended namespaces
# ---------------------------------------------------------------------------
if [[ "$NAMESPACE" != "google-ads-mcp" && "$FORCE_NAMESPACE" != "true" ]]; then
    echo "ERROR: Refusing to uninstall from namespace '$NAMESPACE'." >&2
    echo "       Pass --force-namespace to override this guard." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper: confirm Y/n prompt (returns 0 for yes, 1 for no)
# ---------------------------------------------------------------------------
confirm() {
    local prompt="$1"
    local answer
    read -rp "${prompt} [Y/n]: " answer
    case "${answer:-Y}" in
        [Yy]*) return 0 ;;
        *)     return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# Step 1: Helm uninstall
# ---------------------------------------------------------------------------
echo "==> Uninstalling Helm release '$RELEASE' from namespace '$NAMESPACE'"
if helm status "$RELEASE" -n "$NAMESPACE" &>/dev/null; then
    helm uninstall "$RELEASE" -n "$NAMESPACE"
    echo "    Release uninstalled."
else
    echo "    Release '$RELEASE' not found — skipping helm uninstall."
fi

# ---------------------------------------------------------------------------
# Step 2: Delete Secrets (optional, confirmed)
# ---------------------------------------------------------------------------
SECRETS=(
    google-ads-developer-token
    google-ads-oauth-client
    google-ads-login-customer
)

echo ""
echo "==> The following Secrets may exist in namespace '$NAMESPACE':"
for s in "${SECRETS[@]}"; do
    echo "    - $s"
done
echo ""

if confirm "Delete these Secrets?"; then
    for secret in "${SECRETS[@]}"; do
        if kubectl get secret "$secret" -n "$NAMESPACE" &>/dev/null; then
            kubectl delete secret "$secret" -n "$NAMESPACE"
            echo "    Deleted secret: $secret"
        else
            echo "    Secret not found (already gone): $secret"
        fi
    done
else
    echo "    Skipping Secret deletion."
fi

# ---------------------------------------------------------------------------
# Step 3: Delete namespace (optional, confirmed)
# ---------------------------------------------------------------------------
echo ""
if confirm "Delete namespace '$NAMESPACE'?"; then
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        kubectl delete namespace "$NAMESPACE"
        echo "    Namespace '$NAMESPACE' deleted."
    else
        echo "    Namespace '$NAMESPACE' not found — already gone."
    fi
else
    echo "    Skipping namespace deletion."
fi

echo ""
echo "==> Uninstall complete."
