# MCP HTTP Interoperability Diagnosis

This document describes the verified diagnosis and compatibility changes needed
to run the Google Ads MCP server as a Streamable HTTP service for Antigravity,
Codex CLI 0.146, and clients that implement different MCP protocol revisions.

## Symptoms

Antigravity completed OAuth successfully but failed while loading tools with an
error similar to:

```text
failed to get tools: connection closed: calling "tools/list": client is
closing: sending "subscriptions/listen": failed to connect (session ID: ):
session not found
```

The HTTP trace showed a successful OAuth flow and `initialize` request followed
by a `404 Not Found` response. The client reported that response as a missing
session.

An earlier investigation attributed the failure to a `session_id` query
parameter and to `stateless_http=True`. Inspection of the installed runtime
disproved that explanation. In `mcp 2.0.0`, stateful Streamable HTTP sessions
use the `Mcp-Session-Id` header, and modern protocol requests can be dispatched
without a session.

## Verified root causes

The affected image contained:

- FastMCP `4.0.0b3`;
- `mcp 2.0.0`;
- `google-ads 31.3.0`.

Two independent interoperability problems were reproduced.

### Mixed-generation Streamable HTTP clients

With `stateless_http=True`, a legacy MCP client can no longer open the optional
Streamable HTTP GET channel and receives `405 Method Not Allowed`. A shared
endpoint therefore cannot force stateless mode when it must serve both legacy
and current clients.

The compatible configuration is one `/mcp` endpoint using
`transport="streamable-http"` without enabling `stateless_http`:

- MCP 2025 clients retain POST requests, `Mcp-Session-Id`, and the optional GET
  SSE channel;
- MCP 2026 clients use `server/discover` and sessionless POST requests;
- `stdio` remains the default when HTTP OAuth is not configured.

A permissive CORS middleware added during investigation was removed. No
`OPTIONS` requests were observed, and the local client connects from its own
process rather than from a browser page subject to CORS.

### Missing `subscriptions/listen` handler

After restoring stateful Streamable HTTP, a valid MCP 2026
`subscriptions/listen` request still returned HTTP 404 with a JSON-RPC
`Method not found` error. Antigravity's `mcp-go` client surfaced that response
as `session not found`, including an empty session ID, even though MCP 2026 is
deliberately sessionless.

FastMCP `4.0.0b3` constructed its low-level server without the
`on_subscriptions_listen` handler that the high-level `mcp 2.0.0` server
registers. The compatibility layer in `ads_mcp/coordinator.py` installs a
`ListenHandler` backed by `InMemorySubscriptionBus` only when FastMCP has not
already registered a native handler. This guard makes the workaround removable
when the dependency provides the method itself.

## OAuth compatibility with Codex CLI 0.146

FastMCP `4.0.0b3` advertises
`authorization_response_iss_parameter_supported=true`. Codex CLI 0.146 reaches
the OAuth callback but rejects the result with:

```text
Authorization server response missing required issuer
```

FastMCP includes `iss` in the redirect, so the point at which Codex loses or
fails to recognize it is not observable from the server. The minimum compatible
workaround is to stop advertising the parameter as required.

The Docker build applies a version-guarded replacement only for FastMCP
`4.0.0b3`. It fails if either the installed version or expected source line
changes. This prevents the workaround from being carried silently into a future
dependency version. FastMCP and Codex upgrades must repeat the interoperability
tests and remove the patch when it is no longer needed.

OAuth behavior and MCP transport are separate concerns. Enabling
`stateless_http=True` does not solve the issuer problem and reintroduces the
legacy-client regression.

## OAuth log safety

During diagnosis, the `httpx2` logger emitted the complete token-info request
URL at INFO level. Its query string contained an OAuth access token. No refresh
token was observed.

Server startup now raises only the `httpx2` logger to WARNING before serving
requests. Tests verify the effective logger level. If credentials may have been
captured in local logs, revoking and reauthorizing the Google integration is a
conservative way to invalidate previously issued credentials.

## Validation

The final artifact passed the following checks:

1. The full test suite completed with 53 passing and 3 skipped tests.
2. MCP `2025-03-26` returned `200` and an `Mcp-Session-Id` for `initialize`,
   returned `202` for `notifications/initialized`, listed the configured tools,
   and kept the session's GET SSE channel open with `200`.
3. MCP `2026-07-28` handled `server/discover` and `tools/list` as sessionless
   JSON requests and advertised the same tools.
4. `subscriptions/listen` returned `200 text/event-stream` and emitted
   `notifications/subscriptions/acknowledged`.
5. OAuth authorization-server and protected-resource metadata were published
   correctly. Unauthenticated GET and POST requests to `/mcp` returned `401`
   with `resource_metadata`.
6. Codex CLI 0.146 completed OAuth, loaded all configured tools, and completed a
   read-only `customers_list_accessible_customers` request.
7. Antigravity completed authentication and authorization and displayed the
   server as connected with its tools available.

The configured tools used during validation were:

- `customers_list_accessible_customers`;
- `metadata_get_resource_metadata`;
- `search_search`.

## Local Podman deployment

Build the image from the repository inside WSL:

```shell
podman build --tag localhost/google-ads-mcp:latest --file Dockerfile .
```

Pass Google Ads and OAuth settings through a private environment file, Podman
secrets, or a systemd Quadlet. Do not commit credentials. For local-only agents,
publish port 8080 on the loopback interface and configure clients to use:

```text
http://localhost:8080/mcp
```

The deployed service must start as Streamable HTTP without a `stateless`
marker. Preserve the previously running image under a rollback tag before
promoting a candidate to `latest`. After the service restarts, verify that it is
active, that the container has not entered a restart loop, and that both legacy
and current protocol probes still pass.

## Maintenance constraints

The compatibility behavior depends on the pinned pair `mcp==2.0.0` and
`fastmcp==4.0.0b3`. Any dependency update should verify all of the following
before removing a guard or patch:

- the optional GET channel for stateful MCP 2025 sessions;
- sessionless MCP 2026 discovery and tool calls;
- native handling of `subscriptions/listen`;
- OAuth metadata and callback behavior in supported clients;
- absence of credentials in INFO-level logs.
