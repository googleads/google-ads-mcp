# Roadmap

**Current Milestone:** M1 — Production Deploy
**Status:** Planning

---

## M1 — Production Deploy

**Goal:** `https://google-ads-mcp.qndm.cc/mcp` rodando em produção com TLS
válido, OAuth funcional e CI isolado da branch upstream. Critério de
shippable: 1 comando `helm upgrade --install` + 1 ciclo de upgrade
verificado.

**Target:** primeiro deploy em janela controlada, com tag pinada em
`values.yaml`.

### Features

**Helm Chart Deployment** — IN PROGRESS

- Chart próprio em `helm_chart/google_ads_mcp/` instalável em comando único.
- TLS via `cert-manager` + `letsencrypt-cloudflare` (DNS-01 Cloudflare).
- Modelo de auth OAuth-only via FastMCP `GoogleProvider`.
- Scripts de bootstrap de Secrets (chart só referencia, nunca cria).
- CI GitHub Actions a partir de `quindim/prod` (NÃO `main`).
- Documentação operacional em `helm_chart/README.md`.

Spec: `.specs/features/helm-deployment/spec.md`
Design: `.specs/features/helm-deployment/design.md`
Tasks: `.specs/features/helm-deployment/tasks.md`

---

## M2 — Operational Maturity (futuro)

**Goal:** Fechar gaps que ficaram fora do MVP, sem comprometer a paridade
com upstream.

### Features

**Hardening completo** — PLANNED
- PR upstream para Dockerfile rodar como non-root (`USER nobody` ou similar).
- Habilitar `readOnlyRootFilesystem` com `emptyDir` em `/tmp`.
- Avaliar `NetworkPolicy` quando políticas de cluster forem padronizadas.

**Observability** — PLANNED
- Decidir se vale ServiceMonitor/Prometheus (precisa exporter no FastMCP).
- Avaliar logs estruturados (FastMCP usa stdlib logging hoje).
- Dashboard básico de p95/error rate em Grafana (fonte: stdout do pod).

**CI maduro** — PLANNED
- Lint Helm + `shellcheck` + `actionlint` em PRs que tocam `helm_chart/` e
  `.github/workflows/`.
- `gitleaks` em merges para `quindim/prod` (proteção contra secret vazado).
- (Opcional) Pipeline staging com deploy automático antes de produção.

**Sync com upstream** — PLANNED
- Script ou bot para periodicamente fazer rebase/merge de `main` ←
  `googleads/google-ads-mcp` upstream.
- Política documentada de cherry-pick de patches críticos para
  `quindim/prod` sem trazer features experimentais do upstream.

---

## Future Considerations

- **Multi-cliente OAuth**: vários consumidores OAuth distintos via mesmo
  deploy (per-client redirect URIs, isolamento de quota).
- **Rotação automatizada de OAuth client secret**: External Secrets Operator
  ou Vault sidecar.
- **Migração para Google Ads SDK v25+**: quando upstream pinar; cross-cutting
  em `utils.py`, `tools/`, `resources/`.
- **Auto-scaling**: só relevante se o cluster `quindim` sair de single-node.
- **Multi-region**: irrelevante hoje; nota para futuro.
