#!/usr/bin/env bash
# copy-pull-secret.sh — Copy an image pull secret across namespaces.
#
# Usage:
#   copy-pull-secret.sh [--from-namespace NS] [--to-namespace NS] [--name SECRET]
#
# Options:
#   --from-namespace  Source namespace  (default: quindim-mcp)
#   --to-namespace    Target namespace  (default: google-ads-mcp)
#   --name            Secret name       (default: quindim-registry)

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
FROM_NAMESPACE="quindim-mcp"
TO_NAMESPACE="google-ads-mcp"
SECRET_NAME="quindim-registry"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-namespace)
            FROM_NAMESPACE="${2:?--from-namespace requires a value}"
            shift 2
            ;;
        --to-namespace)
            TO_NAMESPACE="${2:?--to-namespace requires a value}"
            shift 2
            ;;
        --name)
            SECRET_NAME="${2:?--name requires a value}"
            shift 2
            ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Verify source secret exists (fail clearly if not)
# ---------------------------------------------------------------------------
if ! kubectl get secret "$SECRET_NAME" -n "$FROM_NAMESPACE" &>/dev/null; then
    echo "ERROR: Secret '$SECRET_NAME' not found in namespace '$FROM_NAMESPACE'." >&2
    echo "       Verify the name and namespace then retry." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Ensure destination namespace exists
# ---------------------------------------------------------------------------
kubectl create namespace "$TO_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
# Export, strip cluster-specific metadata, and apply in target namespace
# ---------------------------------------------------------------------------
echo "==> Copying secret '$SECRET_NAME' from '$FROM_NAMESPACE' to '$TO_NAMESPACE'"

kubectl get secret "$SECRET_NAME" -n "$FROM_NAMESPACE" -o yaml \
    | python3 -c '
import sys, yaml
d = yaml.safe_load(sys.stdin.read())
for key in ("namespace", "uid", "resourceVersion", "creationTimestamp", "ownerReferences"):
    d.get("metadata", {}).pop(key, None)
print(yaml.dump(d, default_flow_style=False))
' \
    | kubectl apply -n "$TO_NAMESPACE" -f -

echo "==> Done. Secret '$SECRET_NAME' is now available in namespace '$TO_NAMESPACE'."
