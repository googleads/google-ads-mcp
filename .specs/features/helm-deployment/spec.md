# Helm Chart Deployment — google-ads-mcp em Kubernetes

> Fonte: `DEPLOY_SPECS.md` (raiz do repo). Este `spec.md` reformata o conteúdo
> em requisitos rastreáveis (P1/P2/P3 + WHEN/THEN/SHALL + IDs).

## Problem Statement

O `google-ads-mcp` é um fork de `googleads/google-ads-mcp` que precisa rodar em
produção no cluster Kubernetes `quindim` (single-node, k8s 1.28.15) com TLS,
OAuth e CI isolado da branch upstream. Hoje o servidor só roda em modo
local/stdio; sem deploy K8s não há endpoint público
(`https://google-ads-mcp.qndm.cc/mcp`) nem fluxo OAuth viável para clientes
MCP remotos.

## Goals

- [ ] Helm chart próprio em `helm_chart/google_ads_mcp/` instalável com um
      único `helm upgrade --install` após bootstrap.
- [ ] TLS automatizado via `cert-manager` + `letsencrypt-cloudflare` (DNS-01).
- [ ] Modelo de auth **OAuth-only** (sem ADC/SA no cluster) usando o
      `GoogleProvider` do FastMCP.
- [ ] Secrets bootstrapados por scripts em `helm_chart/scripts/`; o chart
      **nunca** cria Secrets — só os referencia (D10/D11).
- [ ] CI GitHub Actions publica
      `registry.quindim.com.br/google-ads-mcp:<tag>` apenas a partir de
      `quindim/prod` (NÃO de `main`, que rastreia o upstream).
- [ ] Documentação operacional em `helm_chart/README.md` (não atualizar o
      `README.md` raiz — ele é mantido idêntico ao upstream).

## Out of Scope

| Feature                                            | Reason                                                                 |
| -------------------------------------------------- | ---------------------------------------------------------------------- |
| HPA / múltiplas réplicas / PodDisruptionBudget     | Cluster single-node; `replicas: 1` é o teto.                           |
| ServiceMonitor / Prometheus                        | FastMCP 3.2.x não expõe `/metrics`; observability via stdout/stderr.  |
| NetworkPolicy                                      | Não exigido pelo cluster atual; egress controlado via DNS público.    |
| `readOnlyRootFilesystem` / `runAsNonRoot`          | Dockerfile upstream roda como root; mudar isso é PR upstream.          |
| Atualização do `README.md` raiz                    | Repo é fork; raiz fica idêntica ao upstream Google.                   |
| CI a partir de `main`                              | `main` sincroniza com upstream; só `quindim/prod` publica imagem.     |
| Deploy automático via CI (`helm` no pipeline)      | Deploy é manual com tag fixa em `values.yaml` ou `--set`.              |
| Suporte a stdio em produção                        | Deploy é exclusivamente HTTP/streamable-http.                          |

---

## User Stories

### P1: Operador instala chart em comando único ⭐ MVP

**User Story**: Como operador da plataforma, quero rodar
`helm upgrade --install google-ads-mcp ./helm_chart/google_ads_mcp -n google-ads-mcp --create-namespace --set image.tag=<TAG>`
e ter o serviço pronto, evitando passos manuais imperativos no cluster.

**Why P1**: Sem instalação automatizada não há deploy. Comando único é o
critério mínimo de "deployable".

**Acceptance Criteria**:
1. WHEN o chart é instalado com `image.tag` definido THEN o sistema SHALL
   criar `Deployment`, `Service`, `Ingress`, `ServiceAccount` e referenciar os
   Secrets externos sem erros.
2. WHEN `image.tag` está vazio THEN o sistema SHALL falhar via `fail` no
   `_helpers.tpl` antes de qualquer apply.
3. WHEN `--create-namespace` é passado e `google-ads-mcp` não existe THEN o
   sistema SHALL criar o namespace.
4. WHEN o Deployment sobe THEN os pods SHALL atingir `Ready` em até 60s
   (probes `tcpSocket :8080`).

**Independent Test**: Bootstrap secrets, executar
`helm upgrade --install ... --set image.tag=<sha>`; confirmar
`kubectl rollout status` retorna sucesso e
`kubectl get pod -n google-ads-mcp` mostra `Running 1/1`.

---

### P1: Serviço acessível em HTTPS com cert válido ⭐ MVP

**User Story**: Como cliente MCP remoto, quero conectar via
`https://google-ads-mcp.qndm.cc/mcp` com certificado confiável, para que a
sessão streamable-http funcione sem warning de TLS.

**Why P1**: OAuth do Google exige HTTPS; sem cert não há login.

**Acceptance Criteria**:
1. WHEN o Ingress é criado THEN cert-manager SHALL emitir certificado via
   `letsencrypt-cloudflare` (DNS-01) e popular o Secret `google-ads-mcp-tls`.
2. WHEN um cliente faz `curl -sI https://google-ads-mcp.qndm.cc/mcp` THEN o
   sistema SHALL responder com cabeçalhos HTTP válidos (status 405 ou 406 em
   GET é esperado para streamable-http).
3. WHEN respostas são streaming/chunked THEN nginx SHALL não bufferizar
   (`proxy-buffering: off`).
4. WHEN payloads atingem 50MB THEN nginx SHALL aceitar (`proxy-body-size`).
5. WHEN requisições demoram até 300s THEN nginx SHALL não derrubar
   (`proxy-read-timeout` / `proxy-send-timeout`).

**Independent Test**: `kubectl get certificate google-ads-mcp-tls -n google-ads-mcp`
reporta `READY=True`; `curl -vI https://google-ads-mcp.qndm.cc` mostra cert
emitido por Let's Encrypt.

---

### P1: OAuth flow end-to-end ⭐ MVP

**User Story**: Como usuário do cliente MCP, quero autenticar via Google OAuth
e ter meu token usado para chamar a Google Ads API, sem que o servidor exija
ADC/SA no cluster.

**Why P1**: É o modelo de auth definido (D6); ADC/SA não foi configurado
intencionalmente.

**Acceptance Criteria**:
1. WHEN o pod sobe com `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` e `_SECRET` injetados
   via `envFrom` THEN `coordinator.py` SHALL construir `GoogleProvider` e o
   servidor SHALL escolher transporte `streamable-http`.
2. WHEN um cliente MCP chega sem token THEN o sistema SHALL redirecionar para
   o OAuth do Google (escopo `adwords`).
3. WHEN o Google redireciona para
   `https://google-ads-mcp.qndm.cc/auth/callback` THEN o sistema SHALL
   completar o handshake e emitir o token MCP.
4. WHEN um tool é chamado com token válido THEN
   `utils._create_credentials()` SHALL preferir `get_access_token()` (não
   cair em ADC).
5. WHEN um tool é chamado sem token e sem ADC THEN o sistema SHALL falhar
   explicitamente (não tentar fallback silencioso).

**Independent Test**: Pelo navegador, abrir
`https://google-ads-mcp.qndm.cc/mcp`; concluir login Google; chamar
`list_accessible_customers` via cliente MCP; verificar resposta com customer
IDs.

---

### P1: Secrets bootstrapados sem valores no repo ⭐ MVP

**User Story**: Como operador, quero rodar
`./helm_chart/scripts/create-secrets.sh --apply` para criar/rotacionar os
Secrets de developer token, OAuth client e (opcional) login customer, sem que
qualquer valor sensível fique em git.

**Why P1**: O repositório é um fork público em produção; secret commitado é
incidente de segurança.

**Acceptance Criteria**:
1. WHEN o script é rodado em modo default (`--dry-run`) THEN o sistema SHALL
   mostrar o YAML resultante sem aplicar.
2. WHEN o script é rodado com `--apply` THEN o sistema SHALL aplicar os 3
   Secrets (`google-ads-developer-token`, `google-ads-oauth-client`,
   opcionalmente `google-ads-login-customer`) no namespace alvo.
3. WHEN os Secrets já existem THEN o sistema SHALL atualizar idempotentemente
   (sem falhar).
4. WHEN o operador roda 2x sem mudar valores THEN a saída SHALL não vazar
   conteúdo (apenas nomes).
5. WHEN `GOOGLE_ADS_LOGIN_CUSTOMER_ID` não é fornecido THEN o sistema SHALL
   pular o Secret `google-ads-login-customer` (uso direto, não-MCC).

**Independent Test**: Rodar script em dry-run; revisar; rodar com `--apply`;
`kubectl get secret -n google-ads-mcp` lista os 3 (ou 2) secrets sem expor
valores.

---

### P1: Hardening parcial do pod ⭐ MVP

**User Story**: Como mantenedor de SecOps, quero o pod com `drop ALL caps`,
`seccomp RuntimeDefault`, `allowPrivilegeEscalation: false` e SA dedicada com
`automountServiceAccountToken: false`, para limitar superfície de ataque mesmo
com Dockerfile rodando como root.

**Why P1**: É o nível de hardening que dá pra fazer sem mudar o Dockerfile
upstream (D18); pular isso é regredir baseline de segurança do cluster.

**Acceptance Criteria**:
1. WHEN o pod sobe THEN o `containers[0].securityContext` SHALL conter
   `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`,
   `seccompProfile.type: RuntimeDefault`.
2. WHEN o pod sobe THEN `serviceAccount.automountServiceAccountToken` SHALL
   ser `false`.
3. WHEN a SA é criada THEN ela SHALL ter nome default `<fullname>` e estar
   referenciada no Deployment.
4. WHEN o operador inspeciona o pod THEN ele SHALL não ter
   `runAsNonRoot: true` (Dockerfile do upstream não suporta — limitação
   conhecida).

**Independent Test**:
`kubectl get pod -n google-ads-mcp -o jsonpath='{.items[0].spec.containers[0].securityContext}'`
mostra os campos esperados.

---

### P2: CI publica imagem só em `quindim/prod`

**User Story**: Como mantenedor do fork, quero que cada push em `quindim/prod`
publique `registry.quindim.com.br/google-ads-mcp:<sha>` (e `:vX.Y.Z` em tag
git), sem que `main` publique nada.

**Why P2**: Sem CI o operador faria build local — risco de divergência. Mas é
possível entregar P1 com push manual da imagem inicialmente.

**Acceptance Criteria**:
1. WHEN há push em `quindim/prod` THEN o workflow
   `.github/workflows/build-image.yaml` SHALL executar build + push.
2. WHEN há push em `main` THEN o workflow SHALL não executar (filtro
   `branches: [quindim/prod]`).
3. WHEN há tag git `vX.Y.Z` em `quindim/prod` THEN o workflow SHALL publicar
   `:vX.Y.Z` adicionalmente ao `:sha-<short>`.
4. WHEN credenciais do registry estão presentes (`REGISTRY_USERNAME` /
   `REGISTRY_PASSWORD`) THEN o login SHALL ter sucesso; ausentes SHALL falhar
   com mensagem clara.

**Independent Test**: Push em `quindim/prod` → ver imagem em
`registry.quindim.com.br/google-ads-mcp:<sha>`; push em `main` → workflow não
roda.

---

### P2: Operador faz upgrade e rollback

**User Story**: Como operador, quero atualizar a versão da imagem com
`helm upgrade --set image.tag=...` e reverter com `helm rollback` se quebrar,
para evitar reinstall.

**Why P2**: Patches/upgrades vão ser frequentes; rollback é rede de segurança.

**Acceptance Criteria**:
1. WHEN `helm upgrade --set image.tag=<NEW>` é executado THEN o Deployment
   SHALL fazer rollout (`RollingUpdate`, `maxSurge: 1`,
   `maxUnavailable: 0`).
2. WHEN o rollout falha (probes nunca ficam Ready) THEN
   `kubectl rollout status` SHALL reportar timeout e o pod novo SHALL não
   substituir o antigo.
3. WHEN `helm rollback google-ads-mcp <REV>` é executado THEN a tag anterior
   SHALL voltar a rodar em < 60s.

**Independent Test**: Upgrade para tag inválida → rollout fica pendente,
antigo continua servindo; rollback restaura.

---

### P2: Rotação de credenciais sem reinstall

**User Story**: Como operador de SecOps, quero rodar o script de secrets de
novo + `kubectl rollout restart` e ver o app pegando as credenciais novas, sem
reinstalar o chart.

**Why P2**: Rotação é processo recorrente; não pode acoplar a release Helm.

**Acceptance Criteria**:
1. WHEN o script é re-executado com novos valores THEN o Secret SHALL ser
   atualizado in-place.
2. WHEN `kubectl rollout restart deploy/google-ads-mcp -n google-ads-mcp` é
   executado THEN os pods SHALL reiniciar e ler o Secret novo via `envFrom`.
3. WHEN apenas o Secret é atualizado SEM rollout THEN os pods existentes
   SHALL continuar usando valores antigos (limitação documentada em
   `helm_chart/README.md`).

**Independent Test**: Mudar developer token; sem restart, request falha 401;
após `rollout restart`, request passa.

---

### P3: Uninstall com guard

**User Story**: Como operador, quero desinstalar via
`./helm_chart/scripts/uninstall.sh` que pede confirmação antes de apagar
Secrets/namespace, para não destruir credenciais por engano.

**Why P3**: Operação rara mas destrutiva; guard é nice-to-have, não MVP.

**Acceptance Criteria**:
1. WHEN o script é rodado com namespace ≠ `google-ads-mcp` SEM
   `--force-namespace` THEN o sistema SHALL abortar.
2. WHEN o script roda THEN ele SHALL pedir confirmação antes de apagar
   Secrets.
3. WHEN o script roda THEN ele SHALL pedir confirmação separada antes de
   apagar o namespace.
4. WHEN o operador responde `n` em qualquer prompt THEN o sistema SHALL parar
   imediatamente.

**Independent Test**: Rodar com namespace diferente → aborta; rodar normal →
2 prompts Y/n; cancelar no segundo prompt → namespace permanece.

---

### P3: Pull secret replicado para namespace alvo

**User Story**: Como operador, quero rodar
`./helm_chart/scripts/copy-pull-secret.sh` para clonar `quindim-registry` do
namespace fonte para `google-ads-mcp`, sem editar YAML manualmente.

**Why P3**: Operação de bootstrap; pode ser feita manualmente em emergência.

**Acceptance Criteria**:
1. WHEN o secret fonte não existe THEN o script SHALL falhar com mensagem
   clara.
2. WHEN o secret destino já existe e é idêntico THEN o script SHALL ser
   silenciosamente bem-sucedido.
3. WHEN o YAML é exportado THEN os campos `metadata.uid`, `resourceVersion`,
   `creationTimestamp`, `ownerReferences`, `namespace` SHALL ser removidos
   antes do apply.

**Independent Test**: Apagar `quindim-registry` no namespace alvo; rodar
script; verificar Secret aparece no namespace correto e a tag `Pod` consegue
puxar a imagem.

---

## Edge Cases

- WHEN o ClusterIssuer `letsencrypt-cloudflare` está com Cloudflare API token
  expirado THEN o cert SHALL ficar `Issuing` indefinidamente (operador checa
  `kubectl describe certificate`).
- WHEN o DNS de `google-ads-mcp.qndm.cc` ainda não propagou THEN o DNS-01
  challenge SHALL falhar e o cert SHALL ficar pendente.
- WHEN o redirect URI no GCP Console diverge de
  `https://google-ads-mcp.qndm.cc/auth/callback` THEN o login SHALL falhar com
  `redirect_uri_mismatch` (não há fallback).
- WHEN `GOOGLE_ADS_MCP_BASE_URL` não bate com `https://<ingress.host>` THEN o
  cookie/redirect OAuth SHALL falhar; `NOTES.txt` SHALL imprimir warning.
- WHEN dois pull-secrets com nomes iguais existem em namespaces diferentes
  THEN o `copy-pull-secret.sh` SHALL preservar a unicidade no destino (apply
  idempotente).
- WHEN o cluster está com pressão de memória (limit `512Mi`) THEN o pod SHALL
  ser OOMKilled — operador ajusta limits via `values.yaml`.
- WHEN o operador faz `helm upgrade` sem `--set image.tag=<NEW>` mantendo o
  default vazio THEN o `_helpers.tpl` SHALL falhar com mensagem clara.

---

## Requirement Traceability

| Requirement ID | Story                                              | Phase  | Status  |
| -------------- | -------------------------------------------------- | ------ | ------- |
| HELM-01        | P1: Install via comando único                      | Design | Pending |
| HELM-02        | P1: `image.tag` obrigatório (fail no helper)       | Design | Pending |
| HELM-03        | P1: Probes `tcpSocket :8080`                       | Design | Pending |
| TLS-01         | P1: Cert via cert-manager DNS-01                   | Design | Pending |
| TLS-02         | P1: Annotations nginx (buffering off, http 1.1, body 50m, timeouts 300s) | Design | Pending |
| OAUTH-01       | P1: `GoogleProvider` em modo HTTP                  | Design | Pending |
| OAUTH-02       | P1: Token OAuth do usuário (sem ADC silencioso)    | Design | Pending |
| OAUTH-03       | P1: Redirect URI fixo `/auth/callback`             | Design | Pending |
| SEC-01         | P1: 3 Secrets bootstrapados via script             | Design | Pending |
| SEC-02         | P1: Apply idempotente do script                    | Design | Pending |
| SEC-03         | P1: Login customer secret opcional                 | Design | Pending |
| SEC-04         | P3: Pull secret replicado de namespace fonte       | Design | Pending |
| CI-01          | P2: Build/push em `quindim/prod` apenas            | Design | Pending |
| CI-02          | P2: Tag git → `:vX.Y.Z`                            | Design | Pending |
| OPS-01         | P2: RollingUpdate `maxSurge=1`/`maxUnavailable=0`  | Design | Pending |
| OPS-02         | P2: `helm rollback` funcional                      | Design | Pending |
| OPS-03         | P2: Rotação via `rollout restart`                  | Design | Pending |
| OPS-04         | P3: Uninstall com guards                           | Design | Pending |
| HARD-01        | P1: SA dedicada, `automountServiceAccountToken: false` | Design | Pending |
| HARD-02        | P1: `containerSecurityContext` (drop caps, seccomp) | Design | Pending |
| DOC-01         | P1: `helm_chart/README.md` operacional             | Design | Pending |

**ID format:** `[CATEGORY]-[NUMBER]` — categorias: `HELM`, `TLS`, `OAUTH`,
`SEC`, `CI`, `OPS`, `HARD`, `DOC`.

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 21 IDs total; 0 mapeados a tasks (Tasks phase ainda não rodou).

---

## Success Criteria

- [ ] `https://google-ads-mcp.qndm.cc/mcp` responde com certificado válido
      emitido por Let's Encrypt.
- [ ] Login Google OAuth completa com `redirect_uri = /auth/callback`.
- [ ] `list_accessible_customers` via cliente MCP retorna sem erros para um
      usuário autenticado.
- [ ] `helm upgrade --install` é o único comando manual após bootstrap (1
      comando, não N).
- [ ] Push em `main` NÃO publica imagem; push em `quindim/prod` SIM.
- [ ] Repositório git não contém valores de secrets (verificável via
      `git log -p` + `gitleaks`).
- [ ] Rotação de OAuth secret + `rollout restart` aplica novas credenciais em
      < 30s.
- [ ] `README.md` raiz do projeto permanece intocado em relação ao upstream
      (diff vazio).
