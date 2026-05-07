# Helm Chart Deployment — Tasks

**Design**: `.specs/features/helm-deployment/design.md`
**Spec**: `.specs/features/helm-deployment/spec.md`
**Status**: Draft

---

## Test Strategy (custom para infra-as-code)

Não há `.specs/codebase/TESTING.md` — esta feature não toca código Python do
app, só Helm/YAML/shell/GitHub Actions. Categorias adaptadas:

| Categoria   | Comando                                                                                       |
| ----------- | --------------------------------------------------------------------------------------------- |
| `lint`      | `helm lint helm_chart/google_ads_mcp/` (chart) + `shellcheck` (scripts) + `actionlint` (CI)   |
| `render`    | `helm template helm_chart/google_ads_mcp/ --debug --set image.tag=test`                      |
| `dry-run`   | `helm template ... \| kubectl apply --dry-run=server -f -` (exige cluster)                    |
| `e2e`       | Deploy real no cluster `quindim`; `kubectl rollout status` + `curl https://...`              |
| `none`      | docs / referência                                                                             |

**Default por task:** lint + render localmente (não exige cluster). E2E acontece manualmente após T7 conforme `DEPLOY_SPECS.md §6.1`.

---

## Execution Plan

```
Phase 1 (Foundation, sequencial):
  T1 ──→ T2

Phase 2 (Implementação paralela):
  T2 completo, então:
    ├── T3 [P]   templates de workload
    ├── T4 [P]   templates de network + NOTES
    ├── T5 [P]   bootstrap scripts (independentes do chart)
    └── T6 [P]   CI workflow (independente)

Phase 3 (Docs final):
  T3, T4, T5, T6 completos, então:
    T7   helm_chart/README.md
```

---

## Task Breakdown

### T1: Chart skeleton + helpers + fail-fast no `image.tag`

**What**: Criar a estrutura mínima do chart Helm — `Chart.yaml`,
`.helmignore` e `templates/_helpers.tpl` com fullname/labels/image helpers
e `fail "image.tag is required"` quando vazio.
**Where**:
- `helm_chart/google_ads_mcp/Chart.yaml`
- `helm_chart/google_ads_mcp/.helmignore`
- `helm_chart/google_ads_mcp/templates/_helpers.tpl`
**Depends on**: None
**Reuses**: Layout padrão `helm create` (sem incluir os defaults de
deployment/service/ingress que o `helm create` gera — substituiremos).
**Requirements**: HELM-01, HELM-02

**Tools**:
- MCP: `context7` (verificar API atual de `Chart.yaml v2` e helpers Sprig se
  necessário).
- Skill: NONE.

**Done when**:
- [ ] `Chart.yaml` com `apiVersion: v2`, `name: google-ads-mcp`,
      `type: application`, `version`, `appVersion`, `kubeVersion: ">=1.28.0-0"`.
- [ ] `_helpers.tpl` define: `google-ads-mcp.fullname`, `.labels`,
      `.selectorLabels`, `.image`, `.serviceAccountName`.
- [ ] `_helpers.tpl` chama `fail "image.tag is required"` quando
      `.Values.image.tag` é vazio.
- [ ] Gate: `helm lint helm_chart/google_ads_mcp/` passa (mesmo com
      templates ainda vazios — Helm permite chart sem recursos).

**Tests**: lint
**Gate**: lint
**Verify**: `helm lint helm_chart/google_ads_mcp/` retorna `0 chart(s) failed`.

**Commit**: `feat(helm): add chart skeleton with image.tag validation`

---

### T2: `values.yaml` + `values.example.yaml` (contrato com operador)

**What**: Definir o contrato de configuração — todas as chaves do
`§5.1 DEPLOY_SPECS.md` com defaults sensatos. Criar versão comentada
`values.example.yaml` para o operador copiar.
**Where**:
- `helm_chart/google_ads_mcp/values.yaml`
- `helm_chart/google_ads_mcp/values.example.yaml`
**Depends on**: T1
**Reuses**: Pattern Bitnami-like (estrutura de chaves
`image/app/secrets/resources/probes/serviceAccount/service/ingress`).
**Requirements**: HELM-01, HELM-02, HELM-03, TLS-02, HARD-01, HARD-02,
OPS-01, SEC-03

**Tools**:
- MCP: NONE.
- Skill: NONE.

**Done when**:
- [ ] `values.yaml` cobre todas as chaves de §5.1 do `DEPLOY_SPECS.md`
      com defaults exatos lá especificados.
- [ ] `image.tag: ""` (forçar override).
- [ ] `ingress.annotations` inclui as 5 mandatórias
      (`proxy-buffering off`, `proxy-http-version 1.1`, `proxy-body-size 50m`,
      `proxy-read-timeout 300`, `proxy-send-timeout 300`).
- [ ] `containerSecurityContext` inclui `allowPrivilegeEscalation: false`,
      `capabilities.drop: ["ALL"]`, `seccompProfile.type: RuntimeDefault`.
- [ ] `serviceAccount.automountServiceAccountToken: false`.
- [ ] `secrets.loginCustomer.enabled: false` (default).
- [ ] `values.example.yaml` é cópia comentada com guidance por chave.
- [ ] Gate: `helm template ... --set image.tag=test` falha SEM essa flag e
      passa COM ela.

**Tests**: lint + render
**Gate**: lint
**Verify**:
```
helm template helm_chart/google_ads_mcp/ 2>&1 | grep -q "image.tag is required"
helm template helm_chart/google_ads_mcp/ --set image.tag=test  # OK
```

**Commit**: `feat(helm): add values.yaml contract with operator defaults`

---

### T3: Templates de workload — Deployment + ServiceAccount + Service [P]

**What**: Implementar `templates/deployment.yaml` (1 replica, envFrom 2-3
Secrets, probes tcpSocket, RollingUpdate), `templates/serviceaccount.yaml`
(automount=false) e `templates/service.yaml` (ClusterIP :8080). Tudo
parametrizado via `values.yaml`.
**Where**:
- `helm_chart/google_ads_mcp/templates/deployment.yaml`
- `helm_chart/google_ads_mcp/templates/serviceaccount.yaml`
- `helm_chart/google_ads_mcp/templates/service.yaml`
**Depends on**: T2
**Reuses**: Helpers do T1 (`google-ads-mcp.fullname`, `.labels`,
`.serviceAccountName`, `.image`).
**Requirements**: HELM-01, HELM-03, OPS-01, OAUTH-01, OAUTH-02, SEC-03,
HARD-01, HARD-02

**Tools**:
- MCP: `context7` (confirmar shape atual de `Deployment.spec.strategy`,
  `tcpSocket` probe, `securityContext` no k8s 1.28).
- Skill: NONE.

**Done when**:
- [ ] `deployment.yaml` tem `replicas: 1`, strategy RollingUpdate
      (`maxSurge: 1`, `maxUnavailable: 0`).
- [ ] `containers[0].command: ["google-ads-mcp"]`,
      `ports: [{name: http, containerPort: 8080}]`.
- [ ] `env`: `PORT=8080`, `GOOGLE_ADS_MCP_BASE_URL`, opcional
      `GOOGLE_ADS_MCP_REDIRECT_PATH` (com toggle), `extraEnv` interpolado
      via `tpl`.
- [ ] `envFrom` lista 2 `secretRef` sempre + 1 condicional
      (`secrets.loginCustomer.enabled`).
- [ ] `livenessProbe` e `readinessProbe` ambos `tcpSocket :http` com
      `initialDelay` / `periodSeconds` do values.
- [ ] `containers[0].securityContext` reflete `containerSecurityContext`
      do values.
- [ ] `imagePullSecrets` injetado de `image.pullSecrets`.
- [ ] `serviceaccount.yaml` cria SA quando `serviceAccount.create=true`
      com `automountServiceAccountToken: false`.
- [ ] `service.yaml` é `ClusterIP`, porta única `8080` → `targetPort: http`.
- [ ] Gate: `helm template --set image.tag=test --debug` renderiza sem
      erros e produz YAML válido para todos os 3 recursos.
- [ ] Gate: `helm template --set image.tag=test --set secrets.loginCustomer.enabled=true`
      adiciona o 3º `secretRef`; com `=false` o `secretRef` não aparece.

**Tests**: lint + render
**Gate**: render
**Verify**:
```
helm template helm_chart/google_ads_mcp/ --set image.tag=test --debug \
  | yq 'select(.kind == "Deployment") | .spec.template.spec.containers[0].envFrom'
helm lint helm_chart/google_ads_mcp/
```

**Commit**: `feat(helm): add deployment, service-account and service templates`

---

### T4: Templates de network — Ingress + NOTES.txt [P]

**What**: Implementar `templates/ingress.yaml` (nginx + TLS via cert-manager
+ 5 annotations mandatórias) e `templates/NOTES.txt` (URL pós-install,
verify commands, warning de inconsistência `baseUrl` vs `host`).
**Where**:
- `helm_chart/google_ads_mcp/templates/ingress.yaml`
- `helm_chart/google_ads_mcp/templates/NOTES.txt`
**Depends on**: T2
**Reuses**: Helpers do T1, `ingress.annotations` do values.
**Requirements**: TLS-01, TLS-02, OAUTH-03, DOC-01 (parcial)

**Tools**:
- MCP: `context7` (confirmar annotations atuais do
  `nginx.ingress.kubernetes.io` e `cert-manager.io/cluster-issuer`).
- Skill: NONE.

**Done when**:
- [ ] `ingress.yaml` com `ingressClassName: nginx`, `tls: [{ hosts: [host],
      secretName: <values.tls.secretName> }]`.
- [ ] Annotations exatas:
      `cert-manager.io/cluster-issuer: <values.tls.clusterIssuer>`,
      `nginx.ingress.kubernetes.io/proxy-buffering: "off"`,
      `proxy-http-version: "1.1"`, `proxy-body-size: "50m"`,
      `proxy-read-timeout: "300"`, `proxy-send-timeout: "300"`.
- [ ] `NOTES.txt` imprime URL `https://{{ .Values.ingress.host }}`.
- [ ] `NOTES.txt` imprime 3 verify commands (`rollout status`,
      `get certificate`, `curl -sI`).
- [ ] `NOTES.txt` emite warning quando `app.baseUrl` ≠
      `https://<ingress.host>`.
- [ ] Gate: `helm template --set image.tag=test --debug` renderiza Ingress
      válido com as 5 annotations mandatórias presentes.

**Tests**: lint + render
**Gate**: render
**Verify**:
```
helm template helm_chart/google_ads_mcp/ --set image.tag=test \
  | yq 'select(.kind == "Ingress") | .metadata.annotations'
# deve listar as 5 annotations
helm install --dry-run --debug test-rel helm_chart/google_ads_mcp/ \
  --set image.tag=test  # NOTES.txt aparece no output
```

**Commit**: `feat(helm): add ingress template and post-install NOTES`

---

### T5: Bootstrap scripts (`create-secrets.sh` + `copy-pull-secret.sh` + `uninstall.sh`) [P]

**What**: Implementar os 3 scripts em `helm_chart/scripts/` (bash, idempotentes,
com guards). Convenção: `create-secrets.sh` interativo+env-override com
`--apply`/`--dry-run`; `copy-pull-secret.sh` clona Secret entre namespaces;
`uninstall.sh` com prompt Y/n e guard de namespace.
**Where**:
- `helm_chart/scripts/create-secrets.sh`
- `helm_chart/scripts/copy-pull-secret.sh`
- `helm_chart/scripts/uninstall.sh`
**Depends on**: None (independente do chart; só precisa concordar nos nomes
dos Secrets — fixos por D10).
**Reuses**: Pattern `kubectl create secret generic --dry-run=client -o yaml | kubectl apply -f -`.
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, OPS-04

**Tools**:
- MCP: NONE.
- Skill: NONE.

**Done when**:
- [ ] Os 3 scripts têm shebang `#!/usr/bin/env bash`, `set -euo pipefail`.
- [ ] Permissões `+x` aplicadas (commitadas em git).
- [ ] `create-secrets.sh` aceita `--namespace`, `--apply` (default
      dry-run); lê valores de env vars com fallback `read -rs`; cria
      namespace se ausente; cria/atualiza idempotentemente os 3 Secrets;
      pula `google-ads-login-customer` se valor vazio; output só lista
      nomes.
- [ ] `copy-pull-secret.sh` aceita `--from-namespace`, `--to-namespace`,
      `--name` (defaults `quindim-mcp` → `google-ads-mcp` /
      `quindim-registry`); falha claramente se source ausente; remove
      `metadata.{namespace,uid,resourceVersion,creationTimestamp,ownerReferences}`
      antes do apply.
- [ ] `uninstall.sh` aceita `--namespace`, `--release`, `--force-namespace`;
      aborta se ns ≠ `google-ads-mcp` sem flag; pede Y/n separado para
      Secrets e namespace; respeita resposta `n`.
- [ ] Gate: `shellcheck helm_chart/scripts/*.sh` sem warnings (severity
      `style` permitido com justificativa inline).
- [ ] Gate (smoke): `bash -n helm_chart/scripts/*.sh` (parse-only) passa.

**Tests**: lint
**Gate**: lint
**Verify**:
```
shellcheck helm_chart/scripts/*.sh
bash -n helm_chart/scripts/create-secrets.sh
bash -n helm_chart/scripts/copy-pull-secret.sh
bash -n helm_chart/scripts/uninstall.sh
# Smoke do create-secrets em modo dry-run com env vars dummy:
GOOGLE_ADS_DEVELOPER_TOKEN=x GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=y \
  GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=z \
  bash helm_chart/scripts/create-secrets.sh --namespace test
# deve imprimir YAML sem aplicar nada
```

**Commit**: `feat(helm): add bootstrap scripts for secrets, pull-secret copy and uninstall`

---

### T6: CI workflow `.github/workflows/build-image.yaml` [P]

**What**: GitHub Actions workflow que builda + publica
`registry.quindim.com.br/google-ads-mcp:<tags>` apenas em `quindim/prod`
(branch + tags `v*.*.*`).
**Where**: `.github/workflows/build-image.yaml`
**Depends on**: None (independente do chart).
**Reuses**: actions oficiais
`docker/setup-buildx-action@v3`, `docker/login-action@v3`,
`docker/metadata-action@v5`, `docker/build-push-action@v5`.
**Requirements**: CI-01, CI-02

**Tools**:
- MCP: `context7` (confirmar versão estável das `docker/*-action`).
- Skill: NONE.

**Done when**:
- [ ] Trigger: `on: { push: { branches: [quindim/prod], tags: ['v*.*.*'] } }`.
- [ ] `concurrency` cancela runs anteriores no mesmo ref.
- [ ] Job `build-and-push` autentica no registry usando Secrets
      `REGISTRY_USERNAME`/`REGISTRY_PASSWORD`.
- [ ] Tags geradas: `sha-<short>` em todo push + `vX.Y.Z` em tag git.
- [ ] Build com Buildx (cache via GH cache backend, opcional).
- [ ] Push: `true`.
- [ ] Gate: `actionlint .github/workflows/build-image.yaml` clean.
      Fallback se `actionlint` indisponível: validar YAML com
      `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/build-image.yaml`.

**Tests**: lint
**Gate**: lint
**Verify**:
```
actionlint .github/workflows/build-image.yaml  # ou python yaml.safe_load
# Pré-requisito documentado: configurar Secrets REGISTRY_USERNAME/PASSWORD
# em GitHub Actions antes do primeiro merge em quindim/prod.
```

**Commit**: `ci(image): build and push image only from quindim/prod`

---

### T7: `helm_chart/README.md` (guia operacional) — NÃO tocar README.md raiz

**What**: Escrever o guia operacional do chart conforme §7 do
`DEPLOY_SPECS.md`: pré-requisitos, layout, tabela de values, tabela de
secrets, comandos copy-paste (bootstrap, install, upgrade, rotação,
uninstall), troubleshooting, refs cruzadas. Reforçar que `README.md` raiz
NÃO deve ser editado.
**Where**: `helm_chart/README.md`
**Depends on**: T2 (tabela de values), T3, T4 (refs aos templates), T5
(comandos dos scripts), T6 (refs ao CI).
**Reuses**: Conteúdo de §7 do `DEPLOY_SPECS.md` adaptado para usuário final.
**Requirements**: DOC-01

**Tools**:
- MCP: NONE.
- Skill: NONE.

**Done when**:
- [ ] Seções 1-8 do plano `DEPLOY_SPECS.md §7` presentes.
- [ ] Tabela de values com colunas
      `Chave / Default / Descrição / Obrigatório?`.
- [ ] Tabela de Secrets com colunas
      `Secret / Tipo / Chaves / Origem`.
- [ ] Troubleshooting cobre: cert pendente, CrashLoopBackOff,
      `redirect_uri_mismatch`, 502/504, `image.tag` faltante.
- [ ] Aviso explícito no topo: "Este NÃO é o README do projeto raiz —
      esse pertence ao upstream Google e não deve ser modificado."
- [ ] `git diff main -- README.md` retorna vazio após este task (sanity
      check de que ninguém tocou no raiz).
- [ ] Gate: `helm-docs` (se disponível) reconcilia tabela de values com
      `values.yaml`. Se indisponível, revisão manual cruzada.

**Tests**: none (docs)
**Gate**: lint (linkcheck básico se possível)
**Verify**:
```
# Confirma raiz intocada:
git diff origin/main..HEAD -- README.md  # deve retornar vazio
# Confirma novo README operacional existe e referencia comandos certos:
grep -q "helm upgrade --install" helm_chart/README.md
grep -q "create-secrets.sh" helm_chart/README.md
grep -q "quindim/prod" helm_chart/README.md
```

**Commit**: `docs(helm): add operator guide for chart deployment`

---

## Parallel Execution Map

```
Phase 1 (Sequential):
  T1 ──→ T2

Phase 2 (Parallel — 4 tasks simultaneous):
  T2 done, then:
    ├── T3 [P]   workload templates
    ├── T4 [P]   network templates + NOTES
    ├── T5 [P]   bootstrap scripts
    └── T6 [P]   CI workflow

Phase 3 (Sequential — depends on all):
  T3, T4, T5, T6 done, then:
    T7   operator README
```

**Parallelism notes:**
- T3, T4, T5, T6 não compartilham arquivos (templates/, scripts/,
  .github/workflows/ são paths disjuntos).
- Gates de cada task são locais (helm lint/template, shellcheck,
  actionlint) — sem dependência de cluster.
- Não há test runtime compartilhado; render do Helm é determinístico por
  task graças a `--set image.tag=test`.

---

## Task Granularity Check

| Task                                | Scope                                   | Status                                                |
| ----------------------------------- | --------------------------------------- | ----------------------------------------------------- |
| T1: Chart skeleton + helpers        | 3 arquivos foundation (cohesivos)       | ✅ Granular (skeleton é uma unidade)                  |
| T2: values.yaml + example           | 2 arquivos (contrato + cópia comentada) | ✅ Granular                                           |
| T3: deployment + sa + service       | 3 templates do mesmo "workload layer"   | ⚠️ Borderline; cohesivo (consolidado a pedido do user) |
| T4: ingress + NOTES                 | 2 templates do "network/post-install"   | ✅ Granular (NOTES referencia ingress.host)           |
| T5: 3 scripts shell                 | 3 scripts independentes mesma família   | ⚠️ Borderline; cohesivo (mesma diretiva, mesmo gate)   |
| T6: CI workflow                     | 1 arquivo                               | ✅ Granular                                           |
| T7: helm_chart/README.md            | 1 arquivo                               | ✅ Granular                                           |

T3 e T5 estão consolidados conforme pedido ("projeto simples, poucas
tasks"). Se a implementação ficar grande, podem ser splitados em T3a/b/c e
T5a/b/c sem mudar dependências.

---

## Diagram-Definition Cross-Check

| Task | `Depends on` (body) | Diagrama mostra | Status |
| ---- | ------------------- | --------------- | ------ |
| T1   | None                | (raiz)          | ✅ Match |
| T2   | T1                  | T1 → T2         | ✅ Match |
| T3   | T2                  | T2 → T3         | ✅ Match |
| T4   | T2                  | T2 → T4         | ✅ Match |
| T5   | None                | (entra em Phase 2 [P], independente de T2) | ⚠️ Diagrama mostra T5 em Phase 2; corpo diz "None". Resolução: T5 PODE rodar em paralelo desde a Phase 1, mas é agrupado em Phase 2 por conveniência operacional (operador faz tudo após contrato T2 estar fixo). Sem violação de dependência. |
| T6   | None                | (idem T5)       | ⚠️ Mesma justificativa |
| T7   | T3, T4, T5, T6      | {T3,T4,T5,T6} → T7 | ✅ Match |

**Decisão:** T5 e T6 marcados em Phase 2 por escolha de cadência (alinha o
agrupamento de paralelismo). Não dependem de T1/T2 tecnicamente; podem ser
adiantados se um sub-agente quiser começar antes.

---

## Test Co-location Validation

Sem `TESTING.md` formal — categorias customizadas (lint/render/dry-run/e2e/none)
declaradas acima. Validação:

| Task | Code Layer Created/Modified                             | Categoria coerente? | Tests field      | Status |
| ---- | ------------------------------------------------------- | ------------------- | ---------------- | ------ |
| T1   | Chart skeleton (sem template aplicável)                  | lint                | lint             | ✅ OK  |
| T2   | values + helpers indiretamente (fail validation)        | lint + render       | lint + render    | ✅ OK  |
| T3   | Templates K8s (Deployment/SA/Service)                   | render              | lint + render    | ✅ OK  |
| T4   | Templates K8s (Ingress) + NOTES                         | render              | lint + render    | ✅ OK  |
| T5   | Shell scripts                                            | lint (shellcheck)   | lint             | ✅ OK  |
| T6   | GitHub Actions YAML                                     | lint (actionlint)   | lint             | ✅ OK  |
| T7   | Markdown                                                 | none / link-check   | none             | ✅ OK  |

E2E real (deploy + curl) é executado **uma vez** após T7 conforme §6.1 do
`DEPLOY_SPECS.md`, fora do ciclo de tasks (operação manual em janela
controlada). Está documentado em T7 mas não conta como gate de fechamento
das tasks.

---

## MCPs e Skills (resposta à pergunta do template)

**MCPs disponíveis neste ambiente** (relevantes para esta feature):
- `context7` — verificar APIs/annotations atuais (cert-manager nginx,
  Helm v2 schema, k8s 1.28). **Uso recomendado em T1, T3, T4, T6**.
- ❌ Não há MCP de Kubernetes — operações `kubectl`/`helm` durante
  Execute usam Bash direto.

**Skills disponíveis** (não há match forte):
- `commit-commands:commit` — usar para criar commits atômicos por task.
- `pr-review-toolkit:review-pr` — após PR criado.
- Nenhum skill específico para Helm/k8s no momento.

---

## Tips de Execute

- **Iterar por phase, commitar por task** — cada task = 1 commit conforme
  formato sugerido.
- **Não criar PR até T7 fechar** — todas as tasks vão para a branch de
  feature, depois 1 PR para `quindim/prod`.
- **Smoke local antes do primeiro deploy real**:
  `helm template --debug --set image.tag=test | kubectl --dry-run=server apply -f -`
  no contexto correto.
- **Pré-requisito manual antes do E2E** (fora de tasks): registrar
  `https://google-ads-mcp.qndm.cc/auth/callback` em "Authorized redirect
  URIs" no GCP Console (DEPLOY_SPECS §2.3).
