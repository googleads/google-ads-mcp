#!/bin/bash

# Google Ads MCP Deployment Script
# Executed by AWS Systems Manager on the EC2 instance (same pattern as
# shopify-partial-payment-app). Pulls the latest image from ECR and restarts
# the container on the shared nginx-proxy network.

set -e  # Exit on any error

echo "=========================================="
echo "Google Ads MCP Deployment Starting"
echo "Time: $(date)"
echo "=========================================="

# Configuration
AWS_REGION="ap-south-1"
COMPOSE_FILE="docker-compose.yml"
ECR_REPOSITORY="qressy-google-ads-mcp"
REPO_DIR="/home/ubuntu/qressy-google-ads-mcp"
DOCKER_CONTAINER_NAME="google-ads-mcp"
DEPLOYMENT_DIR="/home/ubuntu/qressy-google-ads-mcp"
ECR_REGISTRY="953467367422.dkr.ecr.ap-south-1.amazonaws.com"

# Step 0: Configure git safe.directory (prevents ownership errors)
echo "Configuring git safe.directory..."
git config --global --add safe.directory "$REPO_DIR" 2>/dev/null || true

# Step 1: Sync latest code from GitHub
echo "Syncing latest code from GitHub..."
cd "$REPO_DIR"
git pull origin main

if [ $? -eq 0 ]; then
    echo "✓ Code synced successfully"
else
    echo "✗ Git pull failed"
    exit 1
fi

# Change to deployment directory
echo "Navigating to deployment directory: $DEPLOYMENT_DIR"
cd "$DEPLOYMENT_DIR"

# Ensure secrets required at runtime are present on the host
if [ ! -f ".env" ]; then
    echo "✗ .env file not found in $DEPLOYMENT_DIR"
    exit 1
fi
if [ ! -f "service-account-key.json" ]; then
    echo "✗ service-account-key.json not found in $DEPLOYMENT_DIR"
    exit 1
fi

# Step 2: Login to Amazon ECR
echo "Logging into Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY

if [ $? -eq 0 ]; then
    echo "✓ ECR login successful"
else
    echo "✗ ECR login failed"
    exit 1
fi

# Step 3: Pull latest Docker image and restart container
echo "Pulling latest Docker image and restarting container..."
docker compose -f $COMPOSE_FILE up -d --pull always

if [ $? -eq 0 ]; then
    echo "✓ Container updated and restarted successfully"
else
    echo "✗ Container update failed"
    exit 1
fi

# Step 4: Clean up dangling Docker images (safe on shared host)
echo "Cleaning up dangling Docker images..."
docker image prune -f || true


# Step 5: Show container status
echo ""
echo "Current container status:"
docker ps --filter "name=$DOCKER_CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "=========================================="
echo "Deployment completed successfully!"
echo "URL: https://google-ads-mcp.comergent.ai/mcp"
echo "Time: $(date)"
echo "=========================================="
