# DEPLOY_SPECS.md — google-ads-mcp em Kubernetes (cluster `quindim`)

Especificação de deploy do `google-ads-mcp` (FastMCP server) em Kubernetes
de produção via Helm chart próprio. Este documento descreve o **passo a passo**
e os **requisitos técnicos**; nenhum manifest/template é codificado aqui — a
implementação acontece em uma etapa subsequente, sob `./helm_chart/`.

> Escopo do fork: este repositório é um fork de
> `googleads/google-ads-mcp`. **Não atualizar o `README.md` raiz do projeto**
> (mantém-se igual ao upstream). Toda documentação operacional vive em
> `./helm_chart/README.md`.

---

## 1. Decisões consolidadas (entrevista de design)

| # | Decisão | Valor |
|---|---|---|
| D1 | Cluster alvo | `quindim` (single-node, k8s 1.28.15) |
| D2 | Namespace | `google-ads-mcp` (novo, dedicado) |
| D3 | Hostname público (default) | `google-ads-mcp.qndm.cc` (parametrizável) |
| D4 | IngressClass | `nginx` |
| D5 | ClusterIssuer | `letsencrypt-cloudflare` (DNS-01 via Cloudflare) |
| D6 | Modelo de auth | OAuth-only (FastMCP `GoogleProvider`); sem ADC/SA |
| D7 | `LOGIN_CUSTOMER_ID` | Opcional via `values.yaml` |
| D8 | Container registry | `registry.quindim.com.br/google-ads-mcp:<tag>` |
| D9 | imagePullSecret | `quindim-registry` (reaproveitado do cluster) |
| D10 | Secrets | Múltiplos, separados por domínio (estilo `quindim-mcp`) |
| D11 | Bootstrap de Secrets | Scripts em `helm_chart/scripts/` (chart referencia, nunca cria) |
| D12 | CI de imagem | GitHub Actions, **branch `quindim/prod`** (NÃO `main`) |
| D13 | Estratégia de deploy | `helm upgrade --install` manual, tag fixa em `values.yaml` |
| D14 | Replicas | `1` (single-node), sem PDB, sem HPA |
| D15 | Resources | `requests: 100m/256Mi`, `limits: 500m/512Mi` |
| D16 | Probes | `tcpSocket :8080` para liveness e readiness |
| D17 | NetworkPolicy | Não incluir |
| D18 | SecurityContext | Hardening parcial (Dockerfile do upstream roda como root) |
| D19 | ServiceAccount | Dedicada, `automountServiceAccountToken: false` |
| D20 | Annotations nginx | `proxy-buffering off`, `proxy-http-version 1.1`, `proxy-body-size 50m`, `proxy-read/send-timeout 300s` |
| D21 | Observability | stdout/stderr apenas; sem ServiceMonitor/Prometheus |

---

## 2. Pré-requisitos (devem existir antes do `helm install`)

### 2.1 Plataforma / cluster

- [ ] Cluster `quindim` acessível via `kubectl` no contexto correto.
- [ ] `cert-manager` rodando e `ClusterIssuer/letsencrypt-cloudflare` `Ready`.
- [ ] Ingress controller `nginx` (`IngressClass/nginx`) ativo.
- [ ] Pull secret `quindim-registry` disponível em algum namespace fonte
      (o script `copy-pull-secret.sh` o replicará no namespace destino).

### 2.2 DNS

- [ ] Registro `A`/`CNAME` para `google-ads-mcp.qndm.cc` apontando para o IP
      público do ingress controller `nginx` no cluster `quindim`.
- [ ] Zona DNS de `qndm.cc` administrada na Cloudflare (necessário para o
      DNS-01 do `letsencrypt-cloudflare`).

### 2.3 Google Cloud / OAuth

- [ ] Projeto GCP com **Google Ads API** habilitada.
- [ ] Developer Token aprovado (`Basic` ou `Standard` access).
- [ ] OAuth 2.0 Client ID **tipo "Web application"** criado em
      Google Cloud Console > APIs & Services > Credentials.
- [ ] Em "Authorized redirect URIs" do OAuth Client, adicionar:
      `https://google-ads-mcp.qndm.cc/auth/callback`
      (default do `fastmcp.server.auth.providers.google.GoogleProvider`;
      se o `redirect_path` for customizado em `values.yaml`, refletir aqui).
- [ ] Em "Authorized JavaScript origins" (se aplicável):
      `https://google-ads-mcp.qndm.cc`.
- [ ] `Client ID` e `Client Secret` em mãos — entram via
      `scripts/create-secrets.sh`.
- [ ] Caso use Manager Account (MCC): ID numérico do MCC sem hífens
      (ex.: `1234567890`) para `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.

### 2.4 Repositório / CI

- [ ] Branch ativa de produção: `quindim/prod`. **Não usar `main`**
      (sincroniza com upstream Google).
- [ ] Workflow `.github/workflows/build-image.yaml` (a criar na implementação)
      observa `quindim/prod` e publica em
      `registry.quindim.com.br/google-ads-mcp:<git-sha>` e
      `:<semver-tag>`.
- [ ] Credenciais do registry (`REGISTRY_USERNAME`, `REGISTRY_PASSWORD`)
      configuradas como GitHub Actions Secrets.

---

## 3. Arquitetura de deploy

```
                Internet
                    │
                    │ HTTPS (443)
                    ▼
       ┌─────────────────────────┐
       │ ingress-nginx (k8s)     │  TLS via cert-manager + letsencrypt-cloudflare
       │ host: google-ads-mcp.   │  proxy-buffering: off  (streamable-http)
       │       qndm.cc           │  proxy-http-version: 1.1
       └────────────┬────────────┘
                    │  HTTP :8080
                    ▼
            ┌────────────────┐
            │ Service        │ ClusterIP, port 8080
            │ google-ads-mcp │
            └────────┬───────┘
                     │
                     ▼
       ┌────────────────────────────┐
       │ Deployment google-ads-mcp  │ replicas=1
       │  - container :8080         │ readOnly? não (Dockerfile root)
       │  - envFrom Secrets         │ tcpSocket probes
       │  - SA: google-ads-mcp      │ pullSecret: quindim-registry
       └────────────────────────────┘
                     │
   ┌─────────────────┼─────────────────┬───────────────────────┐
   ▼                 ▼                 ▼                       ▼
 Secret          Secret             Secret                  (config via
 google-ads-     google-ads-        google-ads-              values.yaml)
 developer-      oauth-client       login-customer
 token                              (opcional)

                     │  HTTPS (egress)
                     ▼
   - googleads.googleapis.com  (Google Ads API)
   - oauth2.googleapis.com / accounts.google.com  (token validation)
```

Fluxo de uma chamada MCP:

1. Cliente MCP faz `POST https://google-ads-mcp.qndm.cc/mcp` (streamable-http).
2. nginx termina TLS, encaminha p/ Service:8080 sem buffer.
3. FastMCP `GoogleProvider` valida o token OAuth do usuário (escopo `adwords`).
4. Tool handler chama `utils.get_googleads_service(...)`. `_create_credentials()`
   prefere o token OAuth do usuário (per-request); ADC só seria usado como
   fallback (não montaremos SA — em produção falhar é o comportamento desejado).
5. `MCPHeaderInterceptor` adiciona headers de telemetria; resposta em streaming.

---

## 4. Estrutura de arquivos a criar

```
helm_chart/
├── README.md                          ← guia operacional (instalar/upgrade/uninstall)
├── google_ads_mcp/                    ← chart (nome do diretório conforme requisitado)
│   ├── Chart.yaml                     ← apiVersion: v2; name: google-ads-mcp
│   ├── values.yaml                    ← defaults (ver §5.1)
│   ├── values.example.yaml            ← exemplo comentado para operadores
│   ├── .helmignore
│   └── templates/
│       ├── _helpers.tpl               ← labels, fullname, image
│       ├── serviceaccount.yaml        ← SA dedicada, automount=false
│       ├── deployment.yaml            ← Deployment (1 replica, envFrom, probes)
│       ├── service.yaml               ← ClusterIP :8080
│       ├── ingress.yaml               ← Ingress nginx + TLS
│       └── NOTES.txt                  ← saída pós-install (URL, comandos verify)
└── scripts/
    ├── create-secrets.sh              ← cria/atualiza os 3 Secrets (interativo)
    ├── copy-pull-secret.sh            ← clona quindim-registry pra namespace alvo
    └── uninstall.sh                   ← helm uninstall + delete secrets + delete ns (guard)
```

> O chart **não** cria Secrets; ele apenas referencia os Secrets criados pelos
> scripts. Isso garante que o repositório nunca contenha valores sensíveis.

---

## 5. Especificações por componente

### 5.1 `values.yaml` (contrato com o operador)

Chaves a expor no chart (todas com defaults sensatos):

```yaml
# Imagem
image:
  repository: registry.quindim.com.br/google-ads-mcp
  tag: ""                         # obrigatório override; sem default p/ forçar pin
  pullPolicy: IfNotPresent
  pullSecrets:
    - name: quindim-registry

# Aplicação / OAuth
app:
  baseUrl: https://google-ads-mcp.qndm.cc   # = ingress.host com https://
  redirectPath: /auth/callback              # default do GoogleProvider
  loginCustomerId: ""                       # opcional (Manager / MCC)
  extraEnv: []                              # lista de env adicionais

# Secrets (referenciados por envFrom; criados pelos scripts)
secrets:
  developerToken:
    name: google-ads-developer-token        # chave: GOOGLE_ADS_DEVELOPER_TOKEN
  oauthClient:
    name: google-ads-oauth-client           # chaves: GOOGLE_ADS_MCP_OAUTH_CLIENT_ID,
                                            #        GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET
  loginCustomer:
    name: google-ads-login-customer         # chave: GOOGLE_ADS_LOGIN_CUSTOMER_ID
    enabled: false                          # ativar quando MCC

# Workload
replicaCount: 1
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

probes:
  liveness:
    tcpSocket: { port: http }
    initialDelaySeconds: 15
    periodSeconds: 20
    timeoutSeconds: 3
    failureThreshold: 3
  readiness:
    tcpSocket: { port: http }
    initialDelaySeconds: 5
    periodSeconds: 10
    timeoutSeconds: 2
    failureThreshold: 3

# Hardening (Dockerfile do upstream roda como root → não setar runAsNonRoot)
podSecurityContext: {}
containerSecurityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault

serviceAccount:
  create: true
  name: ""                                  # default: <fullname>
  automountServiceAccountToken: false

service:
  type: ClusterIP
  port: 8080

ingress:
  enabled: true
  className: nginx
  host: google-ads-mcp.qndm.cc
  path: /
  pathType: Prefix
  tls:
    enabled: true
    secretName: google-ads-mcp-tls
    clusterIssuer: letsencrypt-cloudflare
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-cloudflare
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-http-version: "1.1"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"

nodeSelector: {}
tolerations: []
affinity: {}
```

**Regras de validação a aplicar no `_helpers.tpl`/`NOTES.txt`:**
- `image.tag` deve ser não-vazio (falhar com `fail` se vazio).
- Se `secrets.loginCustomer.enabled=true`, exigir `app.loginCustomerId` ou
  documentar que o valor virá do Secret (preferível: do Secret).
- Se `app.baseUrl` divergir de `https://<ingress.host><redirect_path>`,
  emitir aviso em `NOTES.txt`.

### 5.2 `Deployment`

- 1 replica, `strategy: RollingUpdate { maxSurge: 1, maxUnavailable: 0 }`.
- `containers[0]`:
  - `name: app`, `image: {{ image.repository }}:{{ image.tag }}`.
  - `command: ["google-ads-mcp"]` (entry point do `pyproject.toml`).
  - `ports: [{ name: http, containerPort: 8080 }]`.
  - `env`:
    - `PORT=8080`
    - `GOOGLE_ADS_MCP_BASE_URL={{ app.baseUrl }}`
    - (opcional) `GOOGLE_ADS_MCP_REDIRECT_PATH={{ app.redirectPath }}` —
      verificar se o app/coordinator lê essa env var; se não ler, propagar via
      `extraEnv` ou via PR upstream (fora do escopo desta spec).
  - `envFrom`:
    - `secretRef: google-ads-developer-token`
    - `secretRef: google-ads-oauth-client`
    - condicional: `secretRef: google-ads-login-customer`
  - `resources`: do values.
  - `livenessProbe`/`readinessProbe`: `tcpSocket :http`.
  - `securityContext`: `containerSecurityContext` do values.
- `serviceAccountName`: SA dedicada.
- `imagePullSecrets`: `quindim-registry`.
- Sem volumes — Dockerfile atual já contém o app; não há writable mounts
  necessários. Se `readOnlyRootFs` for ligado no futuro, montar `emptyDir`
  em `/tmp` (não fazer agora).

### 5.3 `Service`

- `type: ClusterIP`.
- `port: 8080` → `targetPort: http`.
- Sem porta de métricas (não há `/metrics` em FastMCP 3.2.x).

### 5.4 `Ingress`

- `ingressClassName: nginx`.
- `tls: [{ hosts: [<host>], secretName: google-ads-mcp-tls }]` — cert-manager
  cria/renova automaticamente via annotation.
- Annotations exatamente como em `values.yaml § ingress.annotations`.
- `proxy-buffering: off` é **mandatório** para `streamable-http` (SSE/chunked
  streaming não tolera buffering de proxy).

### 5.5 `ServiceAccount`

- Nome default = `<fullname>`.
- `automountServiceAccountToken: false` — a aplicação não fala com a API
  do K8s.

### 5.6 Secrets (criados externamente)

| Secret | Tipo | Chaves | Usado por |
|---|---|---|---|
| `google-ads-developer-token` | `Opaque` | `GOOGLE_ADS_DEVELOPER_TOKEN` | `envFrom` |
| `google-ads-oauth-client`    | `Opaque` | `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID`, `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` | `envFrom` |
| `google-ads-login-customer`  | `Opaque` | `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | `envFrom` (condicional) |
| `quindim-registry`           | `kubernetes.io/dockerconfigjson` | (existing) | `imagePullSecrets` |
| `google-ads-mcp-tls`         | `kubernetes.io/tls` | tls.crt/tls.key | gerado por cert-manager |

### 5.7 Scripts (em `helm_chart/scripts/`)

#### `create-secrets.sh`
- **Inputs:** `--namespace google-ads-mcp` (default), prompts interativos para
  cada valor (com `read -rs` para secret values), com fallback para variáveis de
  ambiente (`GOOGLE_ADS_DEVELOPER_TOKEN`, etc.).
- **Comportamento:**
  - Cria namespace se ausente.
  - Para cada Secret:
    `kubectl -n <ns> create secret generic <name> --from-literal=KEY=VALUE
     --dry-run=client -o yaml | kubectl apply -f -`
    (idempotente — atualiza se existir).
  - Pula `google-ads-login-customer` se valor não for fornecido.
- **Pré:** o operador deve revisar o output antes de pressionar Y para aplicar
  (modo `--dry-run` por default; `--apply` para aplicar).
- **Pós:** imprime resumo dos secrets criados (somente nomes, nunca valores).

#### `copy-pull-secret.sh`
- **Inputs:** `--from-namespace quindim-mcp` (default), `--to-namespace
  google-ads-mcp` (default), `--name quindim-registry`.
- **Comportamento:** `kubectl get secret -n <from> <name> -o yaml` →
  remove `metadata.namespace`, `metadata.uid`, `metadata.resourceVersion`,
  `metadata.creationTimestamp`, `metadata.ownerReferences` →
  `kubectl apply -n <to> -f -`.
- **Edge cases:** falhar se secret fonte não existir; sucesso silencioso se
  destino já existir e for idêntico.

#### `uninstall.sh`
- **Inputs:** `--namespace google-ads-mcp` (default), `--release google-ads-mcp`.
- **Comportamento sequencial:**
  1. `helm uninstall <release> -n <ns>`.
  2. Pergunta confirmação antes de:
     - `kubectl delete secret -n <ns> google-ads-developer-token google-ads-oauth-client google-ads-login-customer quindim-registry --ignore-not-found`
  3. Pergunta confirmação antes de `kubectl delete namespace <ns>`.
- **Guard:** abortar se `<ns>` ≠ `google-ads-mcp` exigir flag `--force-namespace`.

---

## 6. Workflow operacional

### 6.1 Primeira instalação

```
# 0. (CI) build & push da imagem para registry.quindim.com.br/google-ads-mcp:<TAG>
#     a partir da branch quindim/prod.

# 1. Garantir DNS de google-ads-mcp.qndm.cc → ingress IP.

# 2. Garantir OAuth Client com redirect URI
#    https://google-ads-mcp.qndm.cc/auth/callback no GCP.

# 3. Bootstrap do namespace + secrets:
./helm_chart/scripts/copy-pull-secret.sh
./helm_chart/scripts/create-secrets.sh --apply

# 4. Install do chart:
helm upgrade --install google-ads-mcp ./helm_chart/google_ads_mcp \
  -n google-ads-mcp --create-namespace \
  --set image.tag=<TAG>

# 5. Verificações:
kubectl -n google-ads-mcp rollout status deploy/google-ads-mcp
kubectl -n google-ads-mcp get certificate google-ads-mcp-tls   # READY=True
curl -sI https://google-ads-mcp.qndm.cc/mcp                    # 405/406 esperado em GET
```

### 6.2 Upgrade

```
# 1. CI publica nova imagem (ex.: :v0.1.2).
# 2. Atualizar values.yaml ou passar --set image.tag=v0.1.2.
helm upgrade google-ads-mcp ./helm_chart/google_ads_mcp \
  -n google-ads-mcp --set image.tag=v0.1.2
kubectl -n google-ads-mcp rollout status deploy/google-ads-mcp
# 3. Rollback: helm rollback google-ads-mcp <revision>
```

### 6.3 Rotação de credenciais

```
# 1. Re-rodar create-secrets.sh com novos valores (sobrescreve idempotente).
# 2. Forçar restart dos pods para reler envFrom:
kubectl -n google-ads-mcp rollout restart deploy/google-ads-mcp
```

### 6.4 Uninstall

```
./helm_chart/scripts/uninstall.sh
```

---

## 7. Conteúdo planejado de `helm_chart/README.md`

Este README **não é o README do projeto** (que pertence ao upstream Google).
Conterá:

1. Resumo de 1 parágrafo: chart instala google-ads-mcp em modo HTTP/OAuth.
2. **Pré-requisitos** (cluster, DNS, OAuth, registry).
3. Layout de arquivos (`google_ads_mcp/`, `scripts/`).
4. Tabela de `values.yaml` (chave / default / descrição).
5. Tabela de Secrets esperados (nome / chaves / origem).
6. Comandos copy-paste para:
   - bootstrap (`copy-pull-secret.sh`, `create-secrets.sh`),
   - install (`helm upgrade --install ...`),
   - upgrade,
   - uninstall.
7. Troubleshooting:
   - Cert pendente (`kubectl describe certificate ...` / verificar Cloudflare API token do issuer).
   - Pod CrashLoopBackOff por env faltando (verificar `envFrom` e Secrets).
   - 502/504 em respostas longas (proxy timeouts).
   - OAuth: `redirect_uri_mismatch` → checar URI registrada no GCP.
8. Referências cruzadas:
   - Branch de produção: `quindim/prod` (não `main`).
   - Docs upstream para tools/resources MCP: ver `README.md` do projeto.

---

## 8. Itens em aberto / a confirmar na implementação

| # | Item | Onde resolve |
|---|---|---|
| O1 | FastMCP lê `GOOGLE_ADS_MCP_REDIRECT_PATH`? | Inspecionar `coordinator.py` ao codar; se não, manter default `/auth/callback` e aceitar como constraint. |
| O2 | FastMCP em modo http aceita `PORT=8080` ou exige outro env? | Conferir `server.run_server()` no momento da implementação; ajustar manifest. |
| O3 | `google-ads-mcp` precisa de gravação em FS? | Stress test em staging com `readOnlyRootFilesystem=true` num futuro hardening (item para PR upstream). |
| O4 | Cloudflare API token do `letsencrypt-cloudflare` cobre zona `qndm.cc`? | Verificar Secret do ClusterIssuer antes do primeiro deploy. |
| O5 | Path correto do callback no GCP Console | `/auth/callback` (default `GoogleProvider`); se mudar, atualizar consoles. |
| O6 | GitHub Actions tem permissão para push em `registry.quindim.com.br`? | Configurar Secrets `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` ou OIDC equivalente. |
| O7 | Tag strategy do CI | Sugestão: `:sha-<short>` em todo push de `quindim/prod` + `:vX.Y.Z` em tag git. Confirmar no PR de CI. |

---

## 9. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| `proxy-buffering` ligado quebra streaming MCP | Cliente vê resposta truncada/timeout | Annotation `proxy-buffering: off` é mandatória nos defaults. |
| Cert pendente no primeiro install | Sem HTTPS, OAuth quebra (Google exige HTTPS) | Validar issuer antes; alternativa de fallback é `letsencrypt` (HTTP-01). |
| Branch `main` arrasta upstream e contamina prod | Divergência silenciosa | CI **nunca** publica de `main`; documentado em D12 e §2.4. |
| Dockerfile root + readOnlyRootFs causa CrashLoop | Pod não inicia | Hardening parcial em D18: drop caps + seccomp, sem `readOnlyRootFs`/`runAsNonRoot`. |
| Secret rotacionado sem restart | Pod usa credencial antiga indefinidamente | Documentar `kubectl rollout restart` como passo em §6.3. |
| OAuth `redirect_uri_mismatch` | Login falha em produção | Pré-requisito §2.3 lista URIs autorizadas exatas. |

---

## 10. Próximos passos (após aprovação deste spec)

1. Criar estrutura `helm_chart/google_ads_mcp/` e `helm_chart/scripts/`.
2. Implementar templates conforme §5 e scripts conforme §5.7.
3. Implementar `helm_chart/README.md` conforme §7.
4. Adicionar workflow `.github/workflows/build-image.yaml` para `quindim/prod`.
5. Validar com `helm lint` e `helm template --debug` antes do primeiro deploy.
6. Primeiro deploy em janela controlada seguindo §6.1.
