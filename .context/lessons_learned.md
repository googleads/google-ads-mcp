# Lecciones y memoria cruda

## 2026-10-28 — decisiones del usuario

- Reutilizar conexión local y proyecto Google existente. Inspeccionar la conexión antes de proponer alojamiento: Google Cloud OAuth Branding no es alojamiento del MCP.
- Mantener Python/FastMCP, facilitar contribuciones y actualizaciones del oficial; adaptar funciones Rust a Python en módulos separados.
- Confirmar propuestas desde el chat. La obtención de autorización humana depende del cliente y no se demuestra únicamente con un booleano enviado por el asistente.
- No modificar skills/ sin orden explícita. No inventar reglas de AGENTS.md: no se encontró ese archivo.
- El usuario pidió detener implementación y guardar relevo antes de terminar PR/activación. Respetar ese corte y marcar pendientes con precisión.

## 2026-10-28 — hallazgos técnicos verificados

- google-ads 34 selecciona API v26 por defecto; esa llamada devolvió Method not found. v25 explícita funcionó con las credenciales existentes. Evitar que una actualización del SDK cambie silenciosamente la API.
- Campaign usa start_date_time/end_date_time en los tipos instalados; fechas diarias son 00:00:00/23:59:59, en zona de cuenta.
- El contexto de una conexión SQLite no la cierra: cerrar explícitamente para evitar bloqueos de archivos en Windows.
- Atributos protobuf reservados como type requieren type_ al leer con getattr, aunque GAQL use type.
- Un catálogo golden preexistente puede diferir por parsing de docstrings. Se conservaron descripciones explícitas y se actualizó solo el texto de búsqueda extendido ya existente; no relajar pruebas para ocultar diferencias de contrato.
- No declarar APPLIED únicamente porque la API devolvió una respuesta: verificar postcondiciones y conservar resource names incluso si falla esa lectura.
- No reintentar automáticamente mutaciones tras un timeout. Propuestas UNKNOWN/APPLYING/UNVERIFIED necesitan reconciliación de solo lectura; crear sin IDs devueltos requiere inspección manual.
- Las máscaras de actualización deben seleccionar campos hoja. Traducir retiro de entidades a operación remove; ambos ajustes finales aún requieren reejecutar tests.
- Black multiproceso/nox presentó bloqueos en este entorno Windows; probar --workers 1 y revisar procesos del entorno nuevo sin detener la instalación previa.
