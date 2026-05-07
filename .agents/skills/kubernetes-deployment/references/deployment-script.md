# Deployment Script

## Deployment Script

```bash
#!/bin/bash
# deploy-k8s.sh - Deploy to Kubernetes cluster

set -euo pipefail

NAMESPACE="${1:-production}"
DEPLOYMENT="${2:-api-service}"
IMAGE="${3:-myrepo/api-service:latest}"

echo "Deploying $DEPLOYMENT to namespace $NAMESPACE..."

# Check cluster connectivity
kubectl cluster-info

# Create namespace if not exists
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Apply configuration
kubectl apply -f kubernetes-deployment.yaml -n "$NAMESPACE"

# Wait for rollout
echo "Waiting for deployment to rollout..."
kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=5m

# Verify pods are running
echo "Verification:"
kubectl get pods -n "$NAMESPACE" -l "app=$DEPLOYMENT"

# Check service
kubectl get svc -n "$NAMESPACE" -l "app=$DEPLOYMENT"

echo "Deployment complete!"
```
