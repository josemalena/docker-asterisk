Memoria del asistente — Proyecto docker-asterisk

Última actualización: 2026-06-10

Resumen

Breve descripción: Este archivo contiene la memoria del proyecto: decisiones, sucesos relevantes, y una lista priorizada de pendientes (TODO) que el asistente y el equipo pueden consultar y actualizar.

Estructura del archivo
- Decisiones: decisiones tomadas y fecha.
- Incidentes: problemas detectados y su estado.
- Pendientes (TODO): lista priorizada de tareas abiertas.
- Notas rápidas: ideas o recordatorios.


Decisiones

- 2026-05-13: Se optó por rechazar archivos entrantes por WA y enviar un aviso + menú (implementado en `ragapi/app/api_llm.py`).
- 2026-06-10: Roadmap de la vista del agente (Contact Center) Fases 13–26 definido. Diseño completo (modelo de datos, migraciones, APIs, componentes Jinja, JS, UX, riesgos, pruebas, orden) en `deploy/memory/plan_fases_13-26_agente.md`. Regla: NO modificar lo ya implementado; sólo extender.
- 2026-06-10: `_parse_plantilla_row` ya no consulta Oracle por fila. Nueva función `buscar_notificaciones_por_destinos` (rag_db.py) trae todas las notificaciones en una sola consulta por lotes (IN ≤500); las vistas `/respuestas-plantilla` y `/respuestas-plantilla/csv` construyen el mapa una vez. CSV ahora usa `QUOTE_ALL` + helper `_csv_celda` (colapsa saltos de línea).


Incidentes

- Ninguno abierto actualmente.


Pendientes (TODO)

1. Verificar almacenamiento en SQLite de interacciones de menú
   - Estado: en progreso
   - Notas: Se agregó llamada a `guardar_interaccion` para "menu" y payload tipo MENU (en `api_llm.py`).
   - Acción siguiente: ejecutar una consulta en `/opt/rag/app/chatbot.db` dentro del contenedor `ragapi` para confirmar filas.

2. Registrar intentos de envío de archivos (fileUrl/fileName) para auditoría
   - Estado: pendiente
   - Prioridad: media

3. Añadir endpoint `/admin/interacciones` protegido para volcar últimas N interacciones
   - Estado: pendiente
   - Prioridad: alta

4. Implementar handoff para oficiales de servicio (LDAP + webchat)
   - Estado: pendiente
   - Prioridad: alta
   - Descripción: Crear endpoints para login vía LDAP (miembros de grupo específico), cola de handoffs, aceptación/turnado por oficiales y webchat para que el oficial interactúe con el cliente. Mantener almacenamiento en SQLite para auditoría.
   - Pasos:
     1. Crear tabla `handoffs` en SQLite y funciones CRUD.
     2. Implementar endpoints REST: crear, listar pendientes, aceptar, obtener detalle.
     3. Implementar autenticación LDAP y control de sesiones para oficiales.
     4. Crear UI web mínima para que un oficial vea la cola y acepte handoffs (webchat dedicado).
     5. Registrar eventos en SQLite (creación, aceptación, cierre).
   - Resultado esperado: los oficiales pueden iniciar sesión, ver y aceptar handoffs; las interacciones quedan en SQLite bajo la misma DB existente.

5. Vista del Agente / Contact Center — Fases 13–26
   - Estado: en diseño/implementación incremental
   - Prioridad: alta
   - Plan completo: `deploy/memory/plan_fases_13-26_agente.md` (modelo de datos, migraciones, APIs, componentes, JS, UX, riesgos, pruebas, orden).
   - Estado por fase:
     - F13 Asignación de agentes: parcial (cols/funcs base; falta máquina de estados + tomar/liberar/UI)
     - F14 Notas internas: parcial (backend NOTE listo; falta panel UI + GET)
     - F15 Transferencia: parcial (reasigna; falta depto/motivo/historial)
     - F16 SLA · F17 Etiquetas · F18 Colas · F19 Supervisión · F20 Auditoría · F21 KB · F22 Respuestas rápidas · F23 Timeline 360 · F24 Dashboard operacional · F25 IA agentes: pendientes
     - F26 Multicanal: base (`canal`/`canal_origen` existen)
   - Orden recomendado: 13 → 20 → 14/15 → 17 → 16 → 18 → 19 → 22/21 → 23/24 → 25 → 26.


Notas rápidas

- La variable de entorno `SQLITE_DBNAME` apunta a `/opt/rag/app/chatbot.db`.
- ConversationManager usa Redis para historial conversacional; SQLite almacena interacciones para auditoría.


Cómo contribuir

- Para añadir una nueva decisión o pendiente, editar este archivo y añadir la entrada con fecha y responsable.
- Para marcar un pendiente como completado, mover la línea a una sección "Hecho" con la fecha.


Registro de cambios

- 2026-05-14: Creación del archivo de memoria por el asistente.
