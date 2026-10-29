# Progreso — 2026-10-28

## Terminado y verificado

- [x] Descargar fork y crear rama codex/search-mutations desde base oficial.
- [x] Guardar implementación Python de propuestas, Search y negativas con documentación y procedencia.
- [x] Instalar entorno independiente y registrar entrada google-ads-mcp-editing.
- [x] Obtener resultado OK en suite de 92 pruebas (1 omitida), validando ajustes de Build.add.
- [x] Obtener resultado OK en pruebas smoke del catálogo oficial (2 tests OK sin buffer).
- [x] Verificar handshake stdio de la instalación independiente: 15 herramientas expuestas sin llamadas externas.
- [x] Validar consistencia de dependencias con pip check (no broken requirements).
- [x] Validar formateo de código con Black según regla oficial de noxfile (-l 80 --workers 1, 48 archivos limpios).
- [x] Validar script activate-local.ps1 con configuración sintética y generación de backup.
- [x] Ejecutar prueba real de escritura en vivo con autorización del usuario en cuenta 817-686-7605:
  - Creación y verificación de Presupuesto: 15993218572 (4.000 COP, APPLIED y verified en GAQL).
  - Creación y verificación de Campaña Search PAUSED: 24402585279 ([TEST MCP] Campana de Prueba MCP, APPLIED y verified en GAQL).
- [x] Establecer identidad propia de paquete: google-ads-mcp-extended v0.1.0 y Google Ads MCP Extended (Community Edition).
- [x] Cumplir formalmente con la Licencia Apache 2.0 (archivo NOTICE, avisos de modificación 4.b, disclaimer de no afiliación).
- [x] Publicar cambios en GitHub bajo autoría de Edd Vásquez (https://github.com/eddvasquez/google-ads-mcp/tree/codex/search-mutations).
- [x] Activar ruta de ejecución en la configuración real de Codex (~/.codex/config.toml) apuntando a google-ads-mcp-editing.exe con backup creado.

## Estado final
Servidor extendido completamente integrado, activado localmente y respaldado en la nube.
