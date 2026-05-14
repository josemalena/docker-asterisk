Memoria del asistente — Proyecto docker-asterisk

Última actualización: 2026-05-14

Resumen

Breve descripción: Este archivo contiene la memoria del proyecto: decisiones, sucesos relevantes, y una lista priorizada de pendientes (TODO) que el asistente y el equipo pueden consultar y actualizar.

Estructura del archivo
- Decisiones: decisiones tomadas y fecha.
- Incidentes: problemas detectados y su estado.
- Pendientes (TODO): lista priorizada de tareas abiertas.
- Notas rápidas: ideas o recordatorios.


Decisiones

- 2026-05-13: Se optó por rechazar archivos entrantes por WA y enviar un aviso + menú (implementado en `ragapi/app/api_llm.py`).


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


Notas rápidas

- La variable de entorno `SQLITE_DBNAME` apunta a `/opt/rag/app/chatbot.db`.
- ConversationManager usa Redis para historial conversacional; SQLite almacena interacciones para auditoría.


Cómo contribuir

- Para añadir una nueva decisión o pendiente, editar este archivo y añadir la entrada con fecha y responsable.
- Para marcar un pendiente como completado, mover la línea a una sección "Hecho" con la fecha.


Registro de cambios

- 2026-05-14: Creación del archivo de memoria por el asistente.
