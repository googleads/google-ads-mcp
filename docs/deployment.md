# Google Ads MCP Server - Deployment Guide

Deploys like `shopify-partial-payment-app` on the same EC2 + nginx-proxy:
build/push to ECR, then SSM runs `deploy.sh`. Uses the same GitHub secret
names (`EC2_INSTANCE_ID`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), but a
self-contained workflow (no shared-workflows). Routing uses `VIRTUAL_HOST` /
`VIRTUAL_PORT` on the `proxy` network — no per-app Nginx site file.

---

## 1. Overview

| Item           | Value                                             |
| -------------- | ------------------------------------------------- |
| Service URL    | `https://google-ads-mcp.comergent.ai/mcp`         |
| Transport      | Streamable HTTP (`MCP_TRANSPORT=streamable-http`) |
| Container port | `8080` (`VIRTUAL_PORT=8080`)                      |
| ECR repo       | `qressy-google-ads-mcp`                           |
| EC2 folder     | `/home/ubuntu/qressy-google-ads-mcp`              |
| Compose        | `docker-compose.yml`                              |
| Proxy network  | `proxy` (external, shared with other apps)        |

---

## 2. EC2 folder structure

```text
/home/ubuntu/qressy-google-ads-mcp/
├── .env                         # secrets (not in git)
├── service-account-key.json     # GCP SA key (not in git)
├── docker-compose.yml
├── deploy.sh
└── ... (repo checkout)
```

One-time host prerequisites (same as Shopify app):

- Docker + Compose
- External network: `docker network create proxy` (if not already present)
- nginx-proxy (or equivalent) already serving other `VIRTUAL_HOST` apps
- DNS for `google-ads-mcp.comergent.ai` → this EC2
- ECR repository `qressy-google-ads-mcp` in `ap-south-1`

---

## 3. `.env` on EC2

```bash
PORT=8080
HOST=0.0.0.0
MCP_TRANSPORT=streamable-http
GOOGLE_ADS_MCP_BASE_URL=https://google-ads-mcp.comergent.ai

GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_ADS_DEVELOPER_TOKEN=your-developer-token
GOOGLE_ADS_LOGIN_CUSTOMER_ID=your-manager-customer-id
GOOGLE_APPLICATION_CREDENTIALS=/app/service-account-key.json
```

Place `service-account-key.json` next to `.env` on the host (mounted read-only).

---

## 4. Routing (no new Nginx config)

Same pattern as Shopify:

```yaml
environment:
  - VIRTUAL_HOST=google-ads-mcp.comergent.ai
  - VIRTUAL_PORT=8080
networks:
  - proxy
```

The shared nginx-proxy on EC2 picks up the host and terminates TLS like other apps.
Do **not** add a separate `sites-available` config unless you intentionally leave the proxy network.

---

## 5. GitHub Actions

Workflow: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)

Self-contained Python deploy (no shared-workflows). It:

1. Builds the Docker image and pushes to ECR
2. Runs `deploy.sh` on the EC2 instance via **SSM**

### Required GitHub secrets (same names as Shopify partial-payment app)

| Secret                  | Purpose                     |
| ----------------------- | --------------------------- |
| `EC2_INSTANCE_ID`       | Target EC2 instance for SSM |
| `AWS_ACCESS_KEY_ID`     | ECR push + SSM              |
| `AWS_SECRET_ACCESS_KEY` | ECR push + SSM              |

Trigger: **Actions → Build and Push Docker Image → Run workflow**.

---

## 6. What `deploy.sh` does on the instance

1. `git pull origin main`
2. ECR login (`ap-south-1`)
3. `docker compose -f docker-compose-prod.yml up -d --pull always`
4. Prune unused images/containers
5. Print container status

Manual run on EC2:

```bash
cd /home/ubuntu/qressy-google-ads-mcp
./deploy.sh
```

---

## 7. MCP client config

```json
{
  "mcpServers": {
    "google-ads": {
      "url": "https://google-ads-mcp.comergent.ai/mcp"
    }
  }
}
```
