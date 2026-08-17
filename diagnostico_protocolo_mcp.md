# Resumen Técnico: Diagnóstico de Integración MCP Google Ads vs Antigravity IDE

Este documento detalla los hallazgos, cambios realizados, estado actual y conflictos subyacentes entre las librerías utilizados para integrar el servidor `mb-google-ads-mcp` con Antigravity IDE. Ha sido redactado con máximo nivel de detalle técnico para ser compartido con un especialista.

> **Aviso de revisión (2026-08-17):** las secciones 1-5 se conservan como
> registro del diagnóstico previo, pero su explicación del gestor de sesiones
> no corresponde al `mcp 2.0.0` instalado en la imagen analizada. La sección 6
> contiene la revisión verificada y debe considerarse el estado autoritativo.

## 1. Contexto y Síntomas
El objetivo es conectar Antigravity IDE (cliente basado en `mcp-go`) con un contenedor Docker que expone el MCP de Google Ads (servidor basado en `FastMCP` v4.0.0b3).
El usuario experimenta un fallo en la inicialización dentro del IDE con el siguiente error:
`Error: failed to get tools: connection closed: calling "tools/list": client is closing: sending "subscriptions/listen": failed to connect (session ID: ): session not found`

## 2. Estado Actual del Contenedor y Cambios en el Código
El contenedor `google-ads-mcp:latest` se encuentra corriendo a través de `podman`.
Se ha modificado el archivo fuente `ads_mcp/server.py` en la inicialización de FastMCP:

```python
# ads_mcp/server.py
mcp.run(
    transport="streamable-http",
    stateless_http=True, # [AÑADIDO] Intento de forzar modo sin estado
    port=port,
    host="0.0.0.0",
    uvicorn_config={"access_log": True},
)
```

## 3. Análisis del Flujo de Conexión (Logs)
Al observar los logs internos del contenedor mediante `uvicorn`, el flujo que ejecuta `mcp-go` al configurar la URL `http://localhost:8080/mcp` en el IDE es el siguiente:

1. **Descubrimiento OAuth2**: `GET /.well-known/oauth-protected-resource/mcp` (HTTP 200)
2. **Registro de Cliente**: `POST /register` (HTTP 201)
3. **Flujo de Autorización**: `GET /authorize?...` -> `GET /consent?...` -> `POST /consent` -> `GET /auth/callback`
4. **Obtención de Token**: `POST /token` (HTTP 200)
5. **Request MCP Inicial (`initialize`)**: `POST /mcp` (HTTP 200)
6. **Request MCP Secundario (`tools/list` o `subscriptions/listen`)**: `POST /mcp` (HTTP **404 Not Found**)

El error `404 Not Found` devuelto por el servidor HTTP es interpretado por el SDK `mcp-go` como `session not found`.

## 4. Conflicto Interno de Protocolos y Librerías

El problema radica en una grave asimetría de diseño entre cómo **Antigravity (`mcp-go`)** maneja HTTP JSON-RPC y cómo **FastMCP / mcp Python SDK** implementa `streamable-http`.

### A. Comportamiento de Antigravity (`mcp-go`)
- Cuando Antigravity detecta endpoints OAuth, ejecuta el flujo a la perfección y envía las peticiones JSON-RPC vía `POST` directamente a la URL proporcionada.
- Tras el primer `POST /mcp` (que recibe HTTP 200), Antigravity **presuntamente extrae un identificador de sesión** (posiblemente de las cabeceras, la respuesta o la URL devuelta por el servidor) y lo adjunta como query parameter (`?session_id=...`) en la segunda petición `POST /mcp`.
- Antigravity no realiza la petición HTTP `GET` inicial para iniciar un flujo puro de Server-Sent Events (SSE). Solo lanza `POST`.

### B. Comportamiento de FastMCP / `mcp` Python SDK
Al analizar el código interno de `StreamableHTTPSessionManager` en el SDK de Python:

```python
# Extracto de asgi_app en mcp/server/streamable_http_manager.py
request_mcp_session_id = request.query_params.get("session_id")

if request_mcp_session_id is not None and request_mcp_session_id in self._server_instances:
    # Existing session case
    await transport.handle_request(scope, receive, send)
    return

if request_mcp_session_id is None:
    # New session case (crea una nueva sesión en memoria)
    ...
else:
    # Unknown or expired session ID - return 404 per MCP spec
    body = JSONRPCError(..., message="Session not found")
    ...
    return Response(..., status_code=404)
```

**El Conflicto Raíz:**
1. Aunque inyectamos `stateless_http=True` en `FastMCP` (que a su vez pasa `stateless=True` a `StreamableHTTPSessionManager`), la implementación real de `asgi_app` en la librería base de Python **NO parece respetar correctamente la bandera `stateless` para ignorar el `session_id`**.
2. Cuando Antigravity hace el primer `POST /mcp` sin `session_id`, el servidor lo procesa exitosamente ("New session case"), responde al cliente y almacena la sesión localmente, o bien, si está en modo stateless, maneja la petición y la descarta.
3. El cliente Antigravity intenta ser diligente y envía el segundo `POST /mcp?session_id=XYZ`.
4. El servidor extrae el `session_id`. Como la sesión ya fue destruida (por estar en modo stateless) o bien el task en background colapsó silenciosamente, el `session_id` **no se encuentra en `self._server_instances`**.
5. Como resultado, cae en el bloque `else`, devolviendo **HTTP 404 / Session not found**.

### C. Prueba Fallida con `transport="sse"`
Intentamos evadir el manejador de `streamable-http` cambiando a `transport="sse"`. Sin embargo, esto falló porque Antigravity, al recibir `http://localhost:8080/sse` en su configuración, envió la inicialización inicial `POST /sse`, mientras que el servidor FastMCP en modo SSE puro rechaza `POST` en `/sse` (solo permite `GET`, derivando los POSTs a `/messages`). Antigravity obtuvo `405 Method Not Allowed`.

## 5. Conclusión y Recomendación para el Especialista
La incompatibilidad es sistémica:
- Antigravity asume un cliente HTTP JSON-RPC que puede inyectar `session_id` si se lo proveen, o bien, está malinterpretando el transporte y usando `POST` directo.
- FastMCP / mcp-python dependen intrínsecamente de que una petición con `session_id` exista continuamente en memoria `_server_instances` mediante un task en loop. Si el task muere, la sesión desaparece y produce un 404, neutralizando cualquier intento del cliente de continuar.

**Posibles rutas de solución a explorar por el especialista:**
1. **Bypass de Transporte**: Explorar si Antigravity IDE puede utilizar el transporte estándar `stdio` en su lugar de HTTP. (Ej: `"command": "wsl", "args": ["podman", "exec", "-i", "google-ads-mcp", "google-ads-mcp"]`). Esto evitaría el bug de `StreamableHTTPSessionManager`.
2. **Parche en SDK Python**: Reescribir temporalmente `mcp/server/streamable_http_manager.py` dentro del contenedor para ignorar forzosamente el chequeo de `request_mcp_session_id` si `self.stateless` es True, ruteando siempre a un nuevo `handle_request`.
3. **Desactivar OAuth Integrado**: Verificar si el comportamiento de Antigravity cambia si OAuth no se maneja vía interceptores HTTP, delegando el OAuth a inicialización estática.

## 6. Revisión verificada (Codex, 2026-08-17)

### 6.1 Corrección del diagnóstico de sesiones

La imagen problemática `localhost/google-ads-mcp:latest` fue inspeccionada y
contenía FastMCP `4.0.0b3`, `mcp 2.0.0` y `google-ads 31.3.0`. El extracto de
`StreamableHTTPSessionManager` citado en la sección 4.B no coincide con esa
implementación:

- el modo con sesión usa la cabecera HTTP `Mcp-Session-Id`, no el parámetro de
  consulta `session_id` descrito arriba;
- cuando `stateless=True`, el gestor crea un transporte independiente por
  petición antes de aplicar la lógica de sesiones heredada;
- las peticiones MCP modernas (`2026-07-28`) se enrutan a un manejador sin
  sesión antes de decidir entre el modo stateful y stateless heredado.

Por tanto, no está demostrado que Antigravity adjuntase
`?session_id=...`, ni que el SDK ignorase la bandera `stateless`. Esa hipótesis
queda descartada para el runtime inspeccionado.

### 6.2 Causas reproducidas

La configuración autoritativa de Antigravity IDE está en
`C:\Users\brazzi\.gemini\config\mcp_config.json` y define
`google_ads.serverUrl` como `http://localhost:8080/mcp`.

Se reprodujeron dos incompatibilidades independientes:

1. Con `stateless_http=True`, un cliente heredado puede abrir el canal GET
   opcional de Streamable HTTP y recibir `405 Method Not Allowed`. Por eso no
   debe forzarse el modo stateless en un endpoint compartido por clientes MCP
   de distintas generaciones.
2. Después de corregir lo anterior, una petición MCP 2026 válida a
   `subscriptions/listen` devolvía HTTP `404` con el error JSON-RPC
   `Method not found`. Antigravity/mcp-go presentaba ese 404 como
   `session not found` y mostraba un ID de sesión vacío, aunque el transporte
   MCP 2026 es deliberadamente sin sesión.

La segunda causa estaba en FastMCP `4.0.0b3`: construía su servidor de bajo
nivel sin registrar el manejador `on_subscriptions_listen` que sí incorpora el
servidor MCP de alto nivel del SDK Python `mcp 2.0.0`.

### 6.3 Decisión de compatibilidad

La configuración más agnóstica en FastMCP 4 / `mcp 2.0.0` es mantener un único
endpoint `/mcp` con `transport="streamable-http"` y **no** activar
`stateless_http=True`:

- clientes MCP 2025 conservan `POST`, sesiones mediante `Mcp-Session-Id` y el
  canal GET SSE opcional;
- clientes MCP 2026 usan `server/discover` y peticiones POST sin sesión;
- `stdio` sigue siendo el transporte predeterminado cuando no se configura
  OAuth HTTP.

También se retiró el middleware CORS permisivo añadido durante las pruebas. No
había evidencia de peticiones `OPTIONS`, y Antigravity conecta desde su proceso
local, no desde una página web sujeta a CORS.

### 6.4 Evidencia de validación

Se construyó `localhost/google-ads-mcp:ba47210-dual-era`, ID
`12cab6f35c9e...`, y se obtuvieron estos resultados:

1. Suite completa: 50 pruebas correctas y 3 omitidas.
2. MCP `2025-03-26`: `initialize` devolvió `200` y `Mcp-Session-Id`;
   `notifications/initialized` devolvió `202`; `tools/list` devolvió las tres
   herramientas; GET SSE con esa sesión permaneció abierto con `200`.
3. MCP `2026-07-28`: `server/discover` y `tools/list` devolvieron `200` en JSON,
   sin ID de sesión, y anunciaron las mismas tres herramientas.
4. OAuth aislado: los metadatos de autorización y recurso protegido fueron
   publicados correctamente; GET y POST de `/mcp` sin token devolvieron `401`
   con `resource_metadata`.

Tras añadir un guard de compatibilidad que solo registra
`subscriptions/listen` si FastMCP no proporciona uno nativo, la suite aumentó
a 53 pruebas correctas y 3 omitidas. Una prueba de protocolo contra el artefacto
compilado verificó que `subscriptions/listen` responde `200 text/event-stream`
y emite `notifications/subscriptions/acknowledged`. `server/discover` anuncia
además `tools.listChanged=true`.

Las herramientas anunciadas son:

- `customers_list_accessible_customers`;
- `metadata_get_resource_metadata`;
- `search_search`.

### 6.5 Estado desplegado y rollback

El Quadlet instalado declara `Image=localhost/google-ads-mcp:latest`. La imagen
final fue promovida a esa etiqueta y se reinició únicamente
`google-ads-mcp.service`. El contenedor activo ejecuta la imagen
`localhost/google-ads-mcp:ba47210-universal-logsafe-iss`, ID completo
`7583ffe04a2f3a84851f43e3aa65441d4ff10664b976a61f80884a9a18614fbe`, y
arranca como `streamable-http` sin la marca `(stateless)`. La unidad está
`active/running`, con `ExecMainStatus=0` y cero reinicios del contenedor.

Se conservan puntos de rollback para cada etapa relevante:

- `pre-codex-iss-46cb`: imagen `listenfix-logsafe` validada por Antigravity,
  anterior al workaround OAuth de Codex;
- `pre-logsafe-fa66be`: corrección de `subscriptions/listen` anterior al
  endurecimiento de registros;
- `pre-listenfix-12cab6`: transporte dual anterior a la corrección de
  suscripciones;
- `pre-dual-era-558977`: imagen problemática anterior al transporte dual.

### 6.6 Aceptación real de Antigravity

Después de desplegar la corrección de `subscriptions/listen`, el usuario renovó
la autorización de Google, refrescó la conexión en Antigravity y confirmó que
el servidor aparecía en verde y mostraba sus herramientas. Esta aceptación
directa descarta la hipótesis de incompatibilidad sistémica planteada en la
sección 5.

Para validar también el artefacto `listenfix-logsafe`, el usuario cerró la
sesión MCP de Google Ads en Antigravity, ejecutó de nuevo todo el flujo de
autenticación y autorización, y confirmó que el servidor volvió a aparecer en
verde con las herramientas listadas. Tras promover posteriormente la variante
universal que añade el workaround `iss`, el usuario repitió autenticación y
autorización y confirmó de nuevo Antigravity en verde con las herramientas
listadas contra el ID exacto `7583ffe...`. Los dos clientes quedan así
aceptados contra el mismo artefacto desplegado.

### 6.7 Seguridad de registros OAuth

Durante el diagnóstico se detectó que el logger `httpx2` emitía a nivel INFO la
URL completa de la consulta `tokeninfo`, cuyo query string contenía el token de
acceso OAuth. No se observó el refresh token. Se añadió una configuración
explícita que eleva únicamente `httpx2` a nivel WARNING antes de iniciar el
servidor. La suite y una comprobación dentro de la imagen validaron el nivel
efectivo. El reinicio recreó el contenedor, eliminando sus registros locales
anteriores.

Como medida conservadora, el usuario puede revocar y volver a autorizar la
integración de Google para invalidar credenciales emitidas anteriormente; esa
revocación no se ejecuta automáticamente.

### 6.8 Compatibilidad verificada con Codex 0.146

FastMCP `4.0.0b3` publica
`authorization_response_iss_parameter_supported=true`. La antigua imagen
`91beff7-codex0146-iss` solo desactivaba ese indicador para evitar una regresión
OAuth de Codex 0.146; no corregía el transporte.

La regresión se reprodujo de forma concluyente con `codex-cli 0.146.0` y la
imagen final validada por Antigravity: `codex mcp login google_ads` alcanzó el
callback local, pero terminó con
`Authorization server response missing required issuer`. FastMCP construye el
redirect con `iss`, por lo que el punto exacto donde Codex 0.146 pierde o deja
de reconocer el parámetro no es observable desde el servidor. El workaround
mínimo consiste en dejar de anunciar ese parámetro como obligatorio.

Se construyó la candidata
`localhost/google-ads-mcp:ba47210-universal-logsafe-iss`, ID completo
`7583ffe04a2f3a84851f43e3aa65441d4ff10664b976a61f80884a9a18614fbe`.
El `Dockerfile` aplica el mismo reemplazo unívoco que la imagen antigua, pero
exige exactamente FastMCP `4.0.0b3` y falla el build si cambia la versión o la
línea esperada. La candidata superó 53 pruebas (3 omitidas), publicó
`authorization_response_iss_parameter_supported=false` en una instancia OAuth
aislada y conserva una etiqueta explícita del workaround.

La candidata fue promovida a `latest` y la imagen anterior quedó preservada
como `pre-codex-iss-46cb`. Contra el artefacto universal, Codex 0.146 obtuvo los
siguientes resultados:

1. `codex mcp login google_ads` completó el flujo OAuth correctamente;
2. la sesión cargó las tres herramientas configuradas, sin `405`,
   `session not found` ni error de `issuer`;
3. una llamada real y de solo lectura a
   `customers_list_accessible_customers` terminó correctamente y devolvió tres
   clientes accesibles; sus IDs no se mostraron ni documentaron.

El workaround queda deliberadamente acoplado a FastMCP `4.0.0b3` mediante una
aserción de build. Al actualizar FastMCP o Codex se debe volver a probar el flujo
y retirar la capa cuando deje de ser necesaria; nunca debe reintroducirse
`stateless_http=True` para resolver un problema OAuth.
