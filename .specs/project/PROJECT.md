# google-ads-mcp (Quindim Fork)

**Vision:** Operar internamente o `google-ads-mcp` (FastMCP server da Google
Ads API) como serviço hospedado no cluster `quindim`, expondo-o via
HTTPS+OAuth para clientes MCP autorizados — sem ADC/SA no cluster e mantendo
o fork sincronizável com o upstream `googleads/google-ads-mcp`.
**For:** Equipes internas Quindim que consomem Google Ads via clientes MCP
(LLMs, agentes, dashboards) e parceiros autenticados via Google OAuth.
**Solves:** Acesso programático a Google Ads via MCP em produção, com auth
federada por usuário (token OAuth do próprio requisitante propagado para a
API) e isolamento entre cliente MCP e credenciais GCP do operador.

## Goals

- Endpoint público estável `https://google-ads-mcp.qndm.cc/mcp` com TLS
  válido e SLA single-replica (cluster single-node).
- Modelo de auth OAuth-only por requisição (token do usuário usado direto na
  Google Ads API; sem ADC/SA no cluster).
- Branch isolada (`quindim/prod`) com CI próprio, sem contaminar `main` (que
  rastreia o upstream Google).
- Zero secrets em repositório git — bootstrap via scripts no cluster.
- README raiz idêntico ao upstream (toda doc operacional vive em
  `helm_chart/README.md`).

## Tech Stack

**Core:**
- Linguagem: Python 3.10+
- Servidor: FastMCP 3.2.x (transport `streamable-http`; provider
  `GoogleProvider` para OAuth)
- API: `google-ads` Python SDK pinado em **v24** (imports
  `google.ads.googleads.v24.services.types...`)
- Plataforma: Helm 3 + Kubernetes 1.28 (cluster `quindim`, single-node)
- Edge/TLS: ingress-nginx + cert-manager + ClusterIssuer
  `letsencrypt-cloudflare` (DNS-01 via Cloudflare)

**Key dependencies:**
- `fastmcp` — singleton + `GoogleProvider` (escopo `adwords`).
- `google.ads.googleads.v24` — services/types pinados.
- `MCPHeaderInterceptor` (próprio) — telemetria gRPC.
- `google-genai` — só para `nox -s llm_tests`.
- Registry privado `registry.quindim.com.br` (pull secret `quindim-registry`
  reaproveitado do cluster).

## Scope

**v1 includes:**
- Helm chart próprio em `helm_chart/google_ads_mcp/` (1 comando
  `helm upgrade --install`).
- Bootstrap scripts (`create-secrets.sh`, `copy-pull-secret.sh`,
  `uninstall.sh`).
- CI GitHub Actions publicando imagem em `quindim/prod` only.
- Documentação operacional em `helm_chart/README.md`.

**Explicitly out of scope:**
- HPA / multi-replica / PodDisruptionBudget (cluster single-node).
- ServiceMonitor / Prometheus exporter (FastMCP 3.2.x não expõe `/metrics`).
- NetworkPolicy.
- Hardening completo (`runAsNonRoot`, `readOnlyRootFilesystem` — exigem PR
  upstream).
- Atualização do `README.md` raiz (mantém idêntico ao upstream Google).
- CI publicando de `main` (rastreia upstream).
- Deploy automático via CI (deploy é manual com tag pinada).

## Constraints

- **Cluster**: `quindim`, single-node, k8s 1.28.15.
- **Branch**: produção é `quindim/prod`; `main` é mirror do upstream (nunca
  publicar a partir dela).
- **Auth**: OAuth-only no cluster — sem ADC/SA. Request sem token DEVE falhar
  (não há fallback silencioso).
- **API**: Google Ads pinado em v24 (mudar versão = atualização cross-cutting
  em `utils.py`, `tools/`, `resources/`).
- **Registry**: privado, `registry.quindim.com.br` (pull secret
  `quindim-registry`).
- **Hostname**: `google-ads-mcp.qndm.cc` (parametrizável no chart, mas é o
  default e o que está registrado no GCP OAuth Console).
