# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Install dev deps: `pip install -e .[dev]` (provides `nox` and `black`).

- Run server locally (stdio): `google-ads-mcp` after install, or `python -m ads_mcp.server`.
- Run server in HTTP mode: set `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` and `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` before launch — the server auto-switches to `streamable-http` on `0.0.0.0:$PORT` (default 8080).
- Format: `nox -s format` (black, 80-col). Lint check: `nox -s lint`.
- Unit tests across supported Python versions: `nox -s tests`. Single Python version: `nox -s tests-3.12`.
- Run a single test file directly: `python -m unittest tests/tools/search_test.py`.
- Smoke test (verifies registered tools match golden file): `nox -s smoke_tests`. Regenerate golden after intentional tool changes: `nox -s update_smoke_golden`.
- LLM tool-selection smoke test (needs live credentials + `google-genai`): `nox -s llm_tests`.
- Regenerate the GAQL resource list embedded in the `search` tool description: `google-ads-mcp-update-gaql` (writes `ads_mcp/gaql_resources.txt`).

## Required environment variables

- `GOOGLE_ADS_DEVELOPER_TOKEN` — always required.
- `GOOGLE_APPLICATION_CREDENTIALS` or working ADC — required for stdio mode (FastMCP token path is used in HTTP mode).
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` — required only when accessing accounts via a manager.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` / `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` / `GOOGLE_ADS_MCP_BASE_URL` — set together to enable OAuth proxy + HTTP transport.

## Architecture

**FastMCP singleton + side-effect registration.** A single `FastMCP` instance is constructed in `ads_mcp/coordinator.py`. Every tool/resource module decorates against this singleton (`@mcp.tool`, `mcp.add_tool`, `@mcp.resource`). `ads_mcp/server.py` imports those modules purely for their registration side effects (the `# noqa: F401`s) and calls `mcp.run()`. **When adding a new tool or resource module, you must add its import to `ads_mcp/server.py` or it will not be registered.**

**Transport/auth decision happens at import time.** `coordinator.py` reads `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` / `_SECRET` at module load: if both are present it builds a `GoogleProvider` (scopes include `adwords`) and wires it into the `FastMCP` instance; otherwise the instance is unauthenticated. `server.run_server()` then mirrors the same env check to pick `streamable-http` vs stdio. Setting these vars after import is too late.

**Credential resolution is two-tier.** `utils._create_credentials()` tries `fastmcp.server.dependencies.get_access_token()` first — this is the per-request token populated by the OAuth proxy in HTTP mode. If absent (stdio mode, or unauthenticated request), it falls back to ADC with the `adwords` scope. All Google Ads service clients must be obtained via `utils.get_googleads_service(name)`, which attaches `MCPHeaderInterceptor` for usage telemetry — don't call `client.get_service` directly.

**Google Ads API version is pinned to v24.** Type imports look like `google.ads.googleads.v24.services.types...`. Upgrading the API version means updating these imports across `utils.py`, `tools/`, and `resources/`.

**The `search` tool's description is dynamic.** `tools/search.py` reads `ads_mcp/gaql_resources.txt` at import time and embeds the resource list into the tool description so LLMs see valid GAQL targets. If you add new resources or change the file, regenerate via the `google-ads-mcp-update-gaql` script. A missing file does not break startup — the tool ships with a `WARNING` description instead.

**Layout.**
- `ads_mcp/coordinator.py` — `FastMCP` singleton + auth provider.
- `ads_mcp/server.py` — entry point; imports tool/resource modules to trigger registration.
- `ads_mcp/tools/` — `search`, `core` (`list_accessible_customers`), `get_resource_metadata`.
- `ads_mcp/resources/` — `discovery`, `metrics`, `release_notes`, `segments`.
- `ads_mcp/utils.py` — credentials, client factory, proto-to-dict formatting helpers (`format_output_value`, `format_output_row`).
- `ads_mcp/mcp_header_interceptor.py` — gRPC interceptor adding usage-tracking headers.
- `ads_mcp/update_references.py` — script body for regenerating `gaql_resources.txt`.

## Code style

PEP 8, enforced via `black -l 80`. Tests use `unittest` (not pytest); test files must end in `_test.py` to be discovered by `nox -s tests`. The smoke test compares the live registered-tool list against `tests/smoke/golden_tools_list.json` — adding/removing/renaming a tool requires regenerating that golden.
