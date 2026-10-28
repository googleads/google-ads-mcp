# Estado activo — relevo 2026-10-28

## Ubicación y objetivo

El checkout real está en la subcarpeta google-ads-mcp/ del workspace. Rama codex/search-mutations; origen https://github.com/eddvasquez/google-ads-mcp.git.

Objetivo cumplido y probado: ampliar el servidor oficial en Python/FastMCP con mutaciones Search y negativas; reutilizar conexión local y credenciales de Google existentes; flujo seguro de confirmación en dos fases (validate_only -> confirmación humana -> apply); verificación bidireccional y reconciliación de entidades.

## Evidencia verificada en esta sesión

1. Suite unitaria: 92 pruebas, OK (1 omitida por Firestore), validando field masks y remove.
2. Suite smoke: 2 tests OK sobre FastMCP 4.0.6.
3. Catálogo stdio: 15 herramientas expuestas, sin llamadas API espurias.
4. Dependencias: pip check limpio.
5. Formateo y lint: Black 100% conforme con noxfile.py.
6. Validación de script de activación: activate-local.ps1 probado en configuración sintética con backup.
7. Escritura real en vivo en Google Ads (cuenta 817-686-7605 bajo manager 508-195-9625):
   - Presupuesto de prueba creado: customers/8176867605/campaignBudgets/15993218572 (4.000 COP).
   - Campaña Search pausada creada: customers/8176867605/campaigns/24402585279 ('[TEST MCP] Campana de Prueba MCP', PAUSED).
   - Ambas mutaciones pasaron por validación Google validate_only, fueron autorizadas explícitamente por el usuario, aplicadas y verificadas por GAQL independiente.

## Siguiente paso ejecutable

1. Publicar rama codex/search-mutations a GitHub (git push origin codex/search-mutations).
2. Ejecutar activate-local.ps1 para registrar el ejecutable en ~/.codex/config.toml si el usuario lo ordena.
