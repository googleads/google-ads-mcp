> **AVISO:** Este NÃO é o README do projeto raiz (`README.md`). O README
> raiz pertence ao upstream Google (`googleads/google-ads-mcp`) e **não deve
> ser modificado**. Toda documentação operacional de deploy vive aqui, em
> `helm_chart/README.md`.

# google-ads-mcp — Guia Operacional (Helm)

Este chart Helm instala o `google-ads-mcp` em modo HTTP/OAuth em um cluster
Kubernetes. O servidor expõe o protocolo MCP via `streamable-http` em
`https://<host>/mcp`, com TLS provisionado pelo cert-manager e autenticação
OAuth gerenciada pelo FastMCP `GoogleProvider`.

---

## Conteúdo

1. [Pré-requisitos](#1-pré-requisitos)
2. [Layout de arquivos](#2-layout-de-arquivos)
3. [Tabela de values](#3-tabela-de-values)
4. [Secrets esperados](#4-secrets-esperados)
5. [Bootstrap — primeira instalação](#5-bootstrap--primeira-instalação)
6. [Upgrade](#6-upgrade)
7. [Rotação de credenciais](#7-rotação-de-credenciais)
8. [Uninstall](#8-uninstall)
9. [Troubleshooting](#9-troubleshooting)
10. [Referências](#10-referências)

---

## 1. Pré-requisitos

### Cluster

- Kubernetes `>=1.28.0` acessível via `kubectl` no contexto correto.
- `cert-manager` rodando; `ClusterIssuer/letsencrypt-cloudflare` com status `Ready`.
- Ingress controller `nginx` (`IngressClass/nginx`) ativo.
- Pull secret `quindim-registry` disponível em algum namespace fonte (o script
  `copy-pull-secret.sh` o replicará no namespace de destino).

### DNS

- Registro `A` ou `CNAME` para `google-ads-mcp.qndm.cc` apontando para o IP
  público do ingress controller nginx.
- Zona DNS de `qndm.cc` gerenciada no Cloudflare (necessário para o DNS-01 do
  `letsencrypt-cloudflare`).

### Google Cloud / OAuth

- Projeto GCP com **Google Ads API** habilitada.
- Developer Token aprovado (acesso `Basic` ou `Standard`).
- OAuth 2.0 Client ID **tipo "Web application"** criado em
  _Google Cloud Console → APIs & Services → Credentials_.
- Em **Authorized redirect URIs** do OAuth Client, adicionar:
  `https://google-ads-mcp.qndm.cc/auth/callback`
- `Client ID` e `Client Secret` em mãos — entram via `scripts/create-secrets.sh`.
- (Opcional) ID numérico do Manager Account (MCC) sem hífens para
  `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.

### Repositório / CI

- Branch de produção: `quindim/prod`. **Nunca usar `main`** (sincroniza com upstream).
- Workflow `.github/workflows/build-image.yaml` configurado e segredos
  `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` cadastrados no GitHub Actions.

---

## 2. Layout de arquivos

```
helm_chart/
├── README.md                       ← este arquivo
├── google_ads_mcp/                 ← chart Helm
│   ├── Chart.yaml
│   ├── values.yaml                 ← defaults (ver §3)
│   ├── values.example.yaml         ← exemplo comentado para o operador
│   └── templates/
│       ├── _helpers.tpl
│       ├── serviceaccount.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── ingress.yaml
│       └── NOTES.txt
└── scripts/
    ├── create-secrets.sh           ← cria/atualiza os 3 Secrets de app
    ├── copy-pull-secret.sh         ← copia quindim-registry para o namespace
    └── uninstall.sh                ← desinstala release + Secrets + namespace
```

---

## 3. Tabela de values

| Chave | Default | Descrição | Obrigatório? |
|---|---|---|---|
| `image.repository` | `registry.quindim.com.br/google-ads-mcp` | Repositório da imagem | Não |
| `image.tag` | `""` | Tag da imagem — **deve ser sobrescrito** | **Sim** |
| `image.pullPolicy` | `IfNotPresent` | Política de pull | Não |
| `image.pullSecrets` | `[{name: quindim-registry}]` | Lista de imagePullSecrets | Não |
| `app.baseUrl` | `https://google-ads-mcp.qndm.cc` | URL pública do servidor (enviada ao GoogleProvider) | Não |
| `app.redirectPath` | `/auth/callback` | Path do callback OAuth | Não |
| `app.loginCustomerId` | `""` | ID numérico do Manager Account (MCC) | Não |
| `app.extraEnv` | `[]` | Variáveis de ambiente adicionais (lista de `{name, value}`) | Não |
| `secrets.developerToken.name` | `google-ads-developer-token` | Nome do Secret com o Developer Token | Não |
| `secrets.oauthClient.name` | `google-ads-oauth-client` | Nome do Secret com Client ID e Secret | Não |
| `secrets.loginCustomer.name` | `google-ads-login-customer` | Nome do Secret com Login Customer ID | Não |
| `secrets.loginCustomer.enabled` | `false` | Montar Secret de Login Customer no pod | Não |
| `replicaCount` | `1` | Número de réplicas | Não |
| `resources.requests.cpu` | `100m` | CPU request | Não |
| `resources.requests.memory` | `256Mi` | Memory request | Não |
| `resources.limits.cpu` | `500m` | CPU limit | Não |
| `resources.limits.memory` | `512Mi` | Memory limit | Não |
| `probes.liveness.initialDelaySeconds` | `15` | Delay antes da primeira liveness probe | Não |
| `probes.liveness.periodSeconds` | `20` | Intervalo entre liveness probes | Não |
| `probes.readiness.initialDelaySeconds` | `5` | Delay antes da primeira readiness probe | Não |
| `probes.readiness.periodSeconds` | `10` | Intervalo entre readiness probes | Não |
| `containerSecurityContext.allowPrivilegeEscalation` | `false` | Impede escalada de privilégios | Não |
| `containerSecurityContext.capabilities.drop` | `["ALL"]` | Capabilities removidas | Não |
| `containerSecurityContext.seccompProfile.type` | `RuntimeDefault` | Perfil seccomp | Não |
| `serviceAccount.create` | `true` | Criar ServiceAccount dedicada | Não |
| `serviceAccount.name` | `""` | Nome da SA (padrão: fullname do chart) | Não |
| `serviceAccount.automountServiceAccountToken` | `false` | Não montar token da SA no pod | Não |
| `service.type` | `ClusterIP` | Tipo do Service | Não |
| `service.port` | `8080` | Porta do Service | Não |
| `ingress.enabled` | `true` | Criar Ingress | Não |
| `ingress.className` | `nginx` | IngressClass | Não |
| `ingress.host` | `google-ads-mcp.qndm.cc` | Hostname público | Não |
| `ingress.path` | `/` | Path do Ingress | Não |
| `ingress.pathType` | `Prefix` | Tipo de path matching | Não |
| `ingress.tls.enabled` | `true` | Habilitar TLS | Não |
| `ingress.tls.secretName` | `google-ads-mcp-tls` | Nome do Secret TLS (gerenciado pelo cert-manager) | Não |
| `ingress.tls.clusterIssuer` | `letsencrypt-cloudflare` | ClusterIssuer para emissão do certificado | Não |
| `ingress.annotations` | (5 annotations nginx + cert-manager) | Annotations injetadas no Ingress | Não |
| `nodeSelector` | `{}` | Node selector | Não |
| `tolerations` | `[]` | Tolerations | Não |
| `affinity` | `{}` | Affinity rules | Não |

---

## 4. Secrets esperados

O chart **nunca cria Secrets** — ele apenas os referencia via `envFrom`. Use
`scripts/create-secrets.sh` para provisioná-los antes do `helm install`.

| Secret | Tipo | Chaves | Origem |
|---|---|---|---|
| `google-ads-developer-token` | `Opaque` | `GOOGLE_ADS_DEVELOPER_TOKEN` | `create-secrets.sh` |
| `google-ads-oauth-client` | `Opaque` | `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID`, `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` | `create-secrets.sh` |
| `google-ads-login-customer` | `Opaque` | `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | `create-secrets.sh` (opcional — só quando MCC) |
| `quindim-registry` | `kubernetes.io/dockerconfigjson` | _(existente no cluster)_ | `copy-pull-secret.sh` |
| `google-ads-mcp-tls` | `kubernetes.io/tls` | `tls.crt`, `tls.key` | Gerado automaticamente pelo cert-manager |

---

## 5. Bootstrap — primeira instalação

```bash
# 0. (CI) build & push da imagem a partir da branch quindim/prod
#    → registry.quindim.com.br/google-ads-mcp:<TAG>

# 1. Verificar DNS: google-ads-mcp.qndm.cc → IP do ingress nginx
#    e OAuth Client com redirect URI registrada no GCP (ver §1)

# 2. Copiar pull secret para o namespace de destino
./helm_chart/scripts/copy-pull-secret.sh

# 3. Criar Secrets da aplicação (modo dry-run por padrão; --apply para aplicar)
./helm_chart/scripts/create-secrets.sh --apply

# 4. Instalar o chart
helm upgrade --install google-ads-mcp ./helm_chart/google_ads_mcp \
  --namespace google-ads-mcp --create-namespace \
  --set image.tag=<TAG>

# 5. Verificar
kubectl -n google-ads-mcp rollout status deployment/google-ads-mcp
kubectl -n google-ads-mcp get certificate google-ads-mcp-tls   # READY=True
curl -sI https://google-ads-mcp.qndm.cc/mcp                    # 405/406 esperado em GET
```

---

## 6. Upgrade

```bash
# 1. CI publica nova imagem: registry.quindim.com.br/google-ads-mcp:v0.1.2

# 2. Fazer upgrade passando a nova tag
helm upgrade google-ads-mcp ./helm_chart/google_ads_mcp \
  --namespace google-ads-mcp \
  --set image.tag=v0.1.2

# 3. Verificar rollout
kubectl -n google-ads-mcp rollout status deployment/google-ads-mcp

# 4. Rollback se necessário
helm rollback google-ads-mcp <revision> --namespace google-ads-mcp
```

---

## 7. Rotação de credenciais

```bash
# 1. Re-rodar create-secrets.sh com os novos valores (operação idempotente)
./helm_chart/scripts/create-secrets.sh --apply

# 2. Forçar restart do pod para reler envFrom
kubectl -n google-ads-mcp rollout restart deployment/google-ads-mcp

# 3. Verificar
kubectl -n google-ads-mcp rollout status deployment/google-ads-mcp
```

---

## 8. Uninstall

```bash
./helm_chart/scripts/uninstall.sh
# O script pede confirmação separada para deletar Secrets e o namespace.
# Guard: aborta se o namespace não for google-ads-mcp (a menos que --force-namespace).
```

---

## 9. Troubleshooting

### Certificado TLS pendente

**Sintoma:** `kubectl -n google-ads-mcp get certificate google-ads-mcp-tls` mostra `READY=False`.

```bash
kubectl -n google-ads-mcp describe certificate google-ads-mcp-tls
kubectl -n google-ads-mcp describe certificaterequest
kubectl -n cert-manager logs deploy/cert-manager | grep google-ads-mcp
```

**Causas comuns:**
- DNS não propagado ou apontando para o IP errado.
- Cloudflare API token do ClusterIssuer `letsencrypt-cloudflare` sem permissão
  na zona `qndm.cc` — verificar Secret do issuer em `cert-manager`.
- Rate limit do Let's Encrypt (5 certificados/semana por domínio).

---

### Pod em CrashLoopBackOff

**Sintoma:** `kubectl -n google-ads-mcp get pods` mostra `CrashLoopBackOff`.

```bash
kubectl -n google-ads-mcp logs deploy/google-ads-mcp --previous
kubectl -n google-ads-mcp describe pod -l app.kubernetes.io/name=google-ads-mcp
```

**Causas comuns:**
- Secret ausente ou com chave errada — verificar:
  ```bash
  kubectl -n google-ads-mcp get secret google-ads-developer-token google-ads-oauth-client
  ```
- `image.tag` incorreta ou imagem não publicada no registry.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` / `_SECRET` não encontrados no Secret
  `google-ads-oauth-client`.

---

### OAuth: `redirect_uri_mismatch`

**Sintoma:** Ao tentar autenticar, o Google retorna erro `redirect_uri_mismatch`.

**Causa:** A URI de callback registrada no GCP Console não corresponde à URI
que o servidor está usando.

**Fix:** Verificar que `https://google-ads-mcp.qndm.cc/auth/callback` está
listada em **Authorized redirect URIs** do OAuth Client no GCP Console. Se
`app.redirectPath` foi customizado em `values.yaml`, a URI deve refletir esse
valor.

---

### 502 / 504 em respostas longas

**Sintoma:** Clientes MCP recebem erro 502 ou 504 em consultas que demoram.

**Causa:** Proxy timeout ou buffering habilitado no nginx.

**Verificação:**
```bash
kubectl -n google-ads-mcp get ingress google-ads-mcp -o yaml \
  | grep -E "proxy-(buffering|timeout|http-version)"
```

As 5 annotations mandatórias devem estar presentes:
- `proxy-buffering: "off"` — obrigatório para streaming MCP (SSE/chunked).
- `proxy-http-version: "1.1"` — necessário para keep-alive.
- `proxy-body-size: "50m"` — evita rejeição de payloads grandes.
- `proxy-read-timeout: "300"` e `proxy-send-timeout: "300"` — 5 min para queries longas.

---

### `image.tag` faltante

**Sintoma:** `helm install` ou `helm upgrade` falha com:
```
Error: execution error at (google-ads-mcp/templates/_helpers.tpl): image.tag is required
```

**Fix:** Sempre passar `--set image.tag=<TAG>` ou definir `image.tag` em um
arquivo de values customizado. O campo é intencionalmente vazio no `values.yaml`
para forçar o pin de tag — imagens com `latest` são proibidas em produção.

---

## 10. Referências

- **Branch de produção:** `quindim/prod` — **não usar `main`** (sincroniza com o upstream Google).
- **CI de imagem:** `.github/workflows/build-image.yaml` — publica em
  `registry.quindim.com.br/google-ads-mcp` apenas a partir de `quindim/prod`.
- **Spec de deploy:** `DEPLOY_SPECS.md` — decisões de design, arquitetura e
  workflow operacional completos.
- **Docs do projeto (tools/resources MCP):** `README.md` do projeto raiz
  (pertence ao upstream Google — não editar).
- **Scripts de bootstrap:** `helm_chart/scripts/` — `create-secrets.sh`,
  `copy-pull-secret.sh`, `uninstall.sh`.
