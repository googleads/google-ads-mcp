# Estado activo — relevo 2026-10-28

## Ubicación y objetivo

El checkout real está en la subcarpeta google-ads-mcp/ del workspace inicial. Rama codex/search-mutations; origen https://github.com/eddvasquez/google-ads-mcp.git; base 9a78cbdceebae71a6bc8483bdec333695834ef9c. No existe AGENTS.md en el workspace ni en este checkout: no se pudo leer el Protocolo 5. No se modificó skills/.

Objetivo acordado: ampliar el oficial en Python/FastMCP con edición Search y negativas para uso propio/agencia; reutilizar conexión local y credenciales de Google existentes; confirmar propuestas desde chat; mantener posibilidad de contribuciones y actualizaciones upstream. Plan detallado: docs/extensions.md. Fuera de v1: PMax, conversiones, cambio de estrategia de puja de campañas existentes, SaaS y alojamiento remoto.

## Implementación guardada

- ads_mcp/extensions/changes.py: SQLite fuera del repositorio, propuestas con integridad, validación Google validate_only, snapshots, límites por cuenta/moneda, reclamación atómica, aplicación sin reintentos automáticos, verificación y reconciliación de resultados inciertos. Estados inciertos nunca se desbloquean automáticamente. Propuestas caducan en 30 minutos; confianza en el cliente para autorización humana.
- ads_mcp/extensions/search.py: modelos tipados y builders para campañas, presupuestos, grupos, RSA, keywords positivas/negativas y listas compartidas. Nuevas entidades pausadas; importes decimales exactos; validación de Search y CPC manual. Budget compartido muestra campañas afectadas.
- ads_mcp/tools/editing.py: 12 herramientas opcionales, sumadas a las 3 oficiales; perfil de consulta por defecto conservado.
- ads_mcp/extensions/local.py, ads_mcp/editing_tools_config.yaml y entrada google-ads-mcp-editing en pyproject.toml: modo local de edición explícito, rechaza configuración OAuth remota. editing-tools.yaml es perfil opt-in alternativo.
- docs/extensions.md: instalación, aprobación, estados inciertos, límites, procedencia con revisiones fijadas de Marvento/Heyneuron/FGRibreau y mantenimiento upstream. Adaptación Python, sin incorporar Rust.
- constraints-local.txt: google-ads 34.0.0, FastMCP 4.0.6 y MCP 2.3.0, correspondientes al último entorno independiente instalado en .venv/ (ignorado).
- scripts/verify_editing.py: lecturas reales y validate_only de presupuesto sin cambiar importe; cancela la propuesta. Omite CUSTOMER_NOT_ENABLED. Consulta una fila por recurso para comprobar todos los campos. Ejecutar como módulo: python -m scripts.verify_editing --codex-config RUTA.
- scripts/check_local_catalog.py: handshake stdio con ejecutable independiente de edición; no llama a Google.
- scripts/activate-local.ps1: preparado para cambiar únicamente google_ads.command y guardar backup. NO SE HA EJECUTADO.
- utils.py fija API v25, coherente con imports oficiales. El SDK 34 seleccionaba v26 por defecto y el endpoint devolvía Method not found. La prueba real con v25 funcionó.
- Herramientas de lectura usan descripciones explícitas para preservar sus esquemas con versiones recientes de FastMCP. golden_tools_list.json actualiza solo la descripción search_search a los hints extendidos ya existentes en el código; no se cambió el catálogo para esconder nuevas herramientas.

## Evidencia verificada y límite de esa evidencia

- Última suite de unidad: 92 tests, OK, 1 omitido. Resultado en test-results.log (ignorado). Incluye SDK protobuf real y red simulada, duplicados, dinero, permisos/MCC de entrada, expiración, concurrencia, confirmación/cancelación, timeouts, preservación de IDs tras fallo de verificación y modo local.
- Última suite smoke: 2 tests, OK. Resultado en smoke-results.log (ignorado).
- Verificación real Google v25: LIVE_READ_AND_VALIDATE_ONLY_OK; campos de todos los recursos consultados y propuesta de presupuesto validada/cancelada. No se aplicaron cambios publicitarios. Dos cuentas desactivadas se omitieron tras CUSTOMER_NOT_ENABLED. No copiar sus IDs ni credenciales a documentación pública.
- Catálogo stdio instalado: LOCAL_STDIO_CATALOG_OK, 15 herramientas, sin llamadas API. Resultado en catalog-results.log (ignorado).
- pip check pasó antes de cambiar FastMCP de 4.1.4 a 4.0.6; repetir para el entorno final.
- IMPORTANTE: las 92 pruebas fueron ANTERIORES a dos cambios finales en Build.add, search.py: máscaras de actualización por campos hoja y traducción de status REMOVED a operación remove. El catálogo pasó, pero esas dos modificaciones necesitan nueva ejecución de tests antes de dar por cerrada la implementación.

## Punto exacto donde se detuvo

El usuario interrumpió para solicitar relevo antes de terminar entrega/activación. No hay PR, push ni activación de configuración. La conexión actual y la instalación anterior siguen intactas. Existe instalación editable independiente en .venv/, con google-ads-mcp-editing.exe registrado.

La comprobación global nox -s lint quedó bloqueada/falló al ejecutar Black en Windows; un proceso terminó con exit code 4294967295 tras limpieza de procesos. Archivos individuales se formatearon, pero NO se certifica lint global. Se detuvieron únicamente procesos cuya ruta estaba bajo la nueva .venv/Scripts; no se detuvo la instalación anterior. No hay conflictos de merge. git diff --check pasó antes de guardar este relevo.

Las salidas .log y .venv están ignoradas y NO se deben añadir a Git. No hay secretos incorporados. El commit de relevo solicitado guardará un checkpoint de implementación pendiente de verificación final, no una versión lista para activar.

## Siguiente paso ejecutable exacto

Desde este checkout, leer estos tres archivos y ejecutar git status -s y git log -n 3 --oneline; después ejecutar .venv/Scripts/python.exe -m unittest discover --buffer -s tests -p '*_test.py' para verificar las últimas modificaciones de Build.add en ads_mcp/extensions/search.py. Añadir/verificar aserciones de field masks hoja y operación remove, y resolver lint usando Black con --workers 1 (o BLACK_NUM_WORKERS=1) en un proceso nuevo. No activar ni publicar hasta cerrar esos resultados.

Luego: repetir smoke/pip check si hay cambios; revisar limitaciones de aislamiento local y comprobación de efectos; probar activate-local.ps1 con configuración sintética; publicar rama y PR revisable hacia el fork, adjuntarlo al chat, y solo entonces activar ejecutable con backup y solicitar recarga de conexión. No aplicar cambios publicitarios durante pruebas. Si Git necesita identidad, usar identidad explícita del agente; no atribuir commits al usuario sin datos confirmados.
