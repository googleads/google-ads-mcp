# Estado activo — relevo 2026-10-28

## Ubicación y objetivo

El checkout real está en la subcarpeta google-ads-mcp/ del workspace. Rama codex/search-mutations; origen https://github.com/eddvasquez/google-ads-mcp.git.

Objetivo completado:
1. Ampliación del servidor a Google Ads MCP Extended (Community Edition) en Python/FastMCP con mutaciones Search y negativas.
2. Identidad y empaquetado formal (google-ads-mcp-extended v0.1.0) con pleno cumplimiento de Licencia Apache 2.0 (archivo NOTICE, avisos de modificación 4.b, disclaimer de no afiliación con Google LLC en README.md).
3. Verificación técnica de punta a punta: 92 tests unitarios OK, smoke OK, lint con Black OK, handshake de catálogo stdio OK (15 herramientas).
4. Prueba de escritura real en vivo en cuenta 817-686-7605 bajo manager 508-195-9625: presupuesto creado y verificado (15993218572) y campaña Search pausada creada y verificada (24402585279) siguiendo el flujo de seguridad en dos fases (validate_only + confirmación humana explícita).
5. Publicación en GitHub: rama codex/search-mutations sincronizada con autoría asignada a Edd Vásquez.
6. Activación local: servidor MCP actualizado en ~/.codex/config.toml apuntando a google-ads-mcp-editing.exe con backup de seguridad generado.

## Siguiente paso

Recargar la conexión del MCP en el cliente para empezar a utilizar las 15 herramientas (lectura y mutación segura).
