# Plan de diseño — Vista del Agente / Contact Center (Fases 13–26)

Arquitecto de Soluciones Omnicanal · Contact Center · CRM · Customer Service
Última actualización: 2026-06-10

> Regla rectora: **NO** modificar lo ya implementado. Sólo **extender** la
> plataforma existente (Flask + Jinja2 + Bootstrap 5 + SQLite + Redis + Oracle).

## 0. Estado de partida (ya implementado)

Conversaciones · Dashboard · Modal de chat · Adjuntos · Intents · Atención
humana · Handoff Bot/Humano · Solicitud de cédula · OTP · Validación de
cliente · Perfil del cliente · Exportación CSV.

Piezas reutilizables ya presentes en el código:

- Tabla `conversaciones` con: `estado` (default `ABIERTA`), `asignado_a`,
  `prioridad` (default `NORMAL`), `atendido_por`, `fecha_asignacion`,
  `fecha_creacion`, `fecha_ultimo_mensaje`, `fecha_cierre`, `canal`,
  `canal_origen`. → [rag_db.py:286](../ragapi/app/rag_db.py#L286)
- Tabla `mensajes` con `direccion` (IN/OUT/**NOTE**), `enviado_por`,
  `metadata`, soporte de adjuntos.
- Funciones: `marcar_atendido_por`, `obtener_atendido_por`,
  `transferir_conversacion` (sólo reasigna `asignado_a`),
  `guardar_nota_interna` (persiste `direccion='NOTE'`), `cerrar_conversacion`.
- Rutas `/interacciones/...`: ver, enviar, atender, identificar,
  cliente/cuentas/préstamos/certificados/feria, nota, transferir, cerrar.
- Componentes Jinja: `mensajes`, `panel_acciones`, `panel_adjuntos`,
  `panel_cliente`, `panel_intents`; modal `conversacion_modal.html`.
- JS util: `getJSON` en [static/js/util.js:43](../ragapi/app/static/js/util.js#L43).

Implicación: Fases 13/14/15 están **parcialmente** hechas y se completan, no se
reinventan.

---

## 1. Modelo de datos (cross-cutting)

Convención de migración existente: en `crear_db()` se hace
`CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN`
idempotente. **Todas** las migraciones nuevas siguen ese patrón (no romper DBs
en producción).

### Tablas nuevas

```
agentes                 -- catálogo de agentes/usuarios del contact center
  id INTEGER PK
  usuario TEXT UNIQUE         -- = session['usuario']
  nombre TEXT
  rol TEXT DEFAULT 'agente'   -- agente | supervisor
  departamento TEXT
  activo INTEGER DEFAULT 1
  ultimo_visto TIMESTAMP      -- presencia (Fase 19: agentes conectados)

departamentos           -- Fase 15/18
  id INTEGER PK
  nombre TEXT UNIQUE          -- Servicio al cliente, Préstamos, Captaciones, Cobros, Tecnología
  activo INTEGER DEFAULT 1

colas                   -- Fase 18
  id INTEGER PK
  nombre TEXT UNIQUE
  departamento_id INTEGER FK
  estrategia TEXT DEFAULT 'fifo'   -- fifo | prioridad | round_robin
  prioridad INTEGER DEFAULT 0
  activo INTEGER DEFAULT 1

cola_agentes            -- membresía agente<->cola (balanceo/round robin)
  cola_id INTEGER FK
  agente_id INTEGER FK
  rr_orden INTEGER             -- puntero round robin
  PRIMARY KEY (cola_id, agente_id)

asignaciones            -- historial de asignación/toma/liberación (Fase 13)
  id INTEGER PK
  conversacion_id INTEGER FK
  agente TEXT
  accion TEXT                  -- asignar | tomar | liberar | reasignar | escalar
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  detalle TEXT

transferencias          -- Fase 15
  id INTEGER PK
  conversacion_id INTEGER FK
  quien_transfiere TEXT
  quien_recibe TEXT            -- agente destino (NULL si a cola/depto)
  departamento_destino TEXT
  cola_destino INTEGER
  motivo TEXT
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP

etiquetas               -- catálogo (Fase 17)
  id INTEGER PK
  nombre TEXT UNIQUE
  color TEXT
  activo INTEGER DEFAULT 1

conversacion_etiquetas  -- N:M
  conversacion_id INTEGER FK
  etiqueta_id INTEGER FK
  agente TEXT
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  PRIMARY KEY (conversacion_id, etiqueta_id)

sla_config              -- Fase 16 (configurable)
  id INTEGER PK
  metrica TEXT                 -- primera_respuesta | resolucion | espera_cliente
  verde_seg INTEGER            -- <= verde -> verde
  amarillo_seg INTEGER         -- <= amarillo -> amarillo, else rojo
  departamento TEXT            -- NULL = global

sla_eventos             -- Fase 16: marcas de tiempo por conversación
  id INTEGER PK
  conversacion_id INTEGER FK
  primera_respuesta_at TIMESTAMP
  ultimo_mensaje_cliente_at TIMESTAMP
  ultimo_mensaje_agente_at TIMESTAMP
  resolucion_at TIMESTAMP

auditoria               -- Fase 20
  id INTEGER PK
  usuario TEXT
  accion TEXT                  -- inicio_atencion | fin_atencion | transferencia | validacion | consulta_datos | descarga_archivo
  conversacion_id INTEGER
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  detalle TEXT                 -- JSON

kb_articulos            -- Fase 21
  id INTEGER PK
  categoria TEXT               -- Productos | Servicios | Políticas | Procedimientos
  titulo TEXT
  contenido TEXT
  tags TEXT
  activo INTEGER DEFAULT 1
  fecha_actualizacion TIMESTAMP

respuestas_rapidas      -- Fase 22
  id INTEGER PK
  categoria TEXT               -- Saludo | Despedida | Validación | Seguimiento | Cobros
  titulo TEXT
  plantilla TEXT               -- soporta {{nombre}} {{telefono}} {{cod_persona}}
  agente TEXT                  -- NULL = global
  activo INTEGER DEFAULT 1
```

### Columnas añadidas a tablas existentes

```
conversaciones:
  + estado_workflow TEXT DEFAULT 'NUEVA'   -- NUEVA|EN_COLA|ASIGNADA|EN_ATENCION|ESCALADA|CERRADA
                                           -- (NO tocar 'estado' ABIERTA/CERRADA legado; nueva col paralela)
  + cola_id INTEGER
  + departamento TEXT
  + sentimiento TEXT                       -- Fase 25 (positivo|neutral|negativo)
  + resumen TEXT                           -- Fase 25 (resumen IA cacheado)
```

> Nota de compatibilidad: se mantiene `estado` legado y se agrega
> `estado_workflow` para la máquina de estados nueva, evitando romper queries
> existentes. Un backfill marca `estado_workflow` desde `atendido_por`/`estado`.

---

## 2. Fases — diseño por fase

### FASE 13 — Asignación de agentes  *(parcial → completar)*
- **Máquina de estados** `estado_workflow`: NUEVA → EN_COLA → ASIGNADA →
  EN_ATENCION → (ESCALADA) → CERRADA. Transiciones validadas en helper
  `cambiar_estado_workflow(conv_id, nuevo, agente)`.
- Acciones: **asignar** (a agente), **reasignar**, **tomar** (self-assign +
  EN_ATENCION), **liberar** (vuelve a EN_COLA, `asignado_a=NULL`). Cada una
  escribe en `asignaciones` y `auditoria`.
- Reutiliza `asignado_a` + `fecha_asignacion` (ya existen).
- Mostrar en dashboard: columna agente + estado (badge por color).
- APIs: `POST /interacciones/conversacion/<id>/asignar` (body: agente),
  `.../tomar`, `.../liberar`, `.../reasignar`.

### FASE 14 — Notas internas  *(parcial → completar UI)*
- Backend ya guarda `direccion='NOTE'` (no se envía al cliente). Falta:
  **panel independiente** con autor/fecha/texto e historial.
- API: `GET /interacciones/conversacion/<id>/notas` (filtra `direccion='NOTE'`).
- Componente: `components/panel_notas.html` (lista + textarea + botón).
- UX: pestaña/acordeón aparte del hilo de chat; estilo visual distinto (amarillo).

### FASE 15 — Transferencia  *(parcial → completar)*
- Ampliar `transferir_conversacion` para registrar en tabla `transferencias`
  (`quien_transfiere`, `quien_recibe`, `departamento_destino`/`cola_destino`,
  `motivo`) y mantener historial.
- Transferencia entre **agentes** y entre **departamentos**
  (Servicio al cliente, Préstamos, Captaciones, Cobros, Tecnología).
- API: extender `POST .../transferir` con `motivo`, `departamento`/`agente`.
- UX: modal de transferencia (select destino + motivo obligatorio).

### FASE 16 — SLA
- Captura de marcas en `sla_eventos` mediante hooks en envío/recepción de
  mensajes (sin tocar la lógica de entrega: sólo registrar timestamps).
- Métricas: primera respuesta, promedio respuesta, resolución, espera cliente.
- **Semáforo** verde/amarillo/rojo según `sla_config` (configurable, por depto).
- API: `GET /sla/conversacion/<id>`, `GET /sla/resumen?desde&hasta&depto`.
- UX: badge semáforo en dashboard y en el modal.

### FASE 17 — Etiquetas
- N:M `conversacion_etiquetas`. Catálogo en `etiquetas`
  (Queja, Reclamo, Felicitación, Préstamos, Captaciones, Feria, Tarjetas, ATM,
  Tecnología).
- APIs: `GET/POST/DELETE /interacciones/conversacion/<id>/etiquetas`,
  `GET /etiquetas` (catálogo), filtro `?etiqueta=` en listado.
- UX: chips multi-select en modal; filtro en dashboard.

### FASE 18 — Colas
- Tablas `colas`, `cola_agentes`. Estrategias: `fifo`, `prioridad`,
  `round_robin` (puntero `rr_orden`). Asignación automática al entrar a cola.
- Helper `enrutar_a_cola(conv_id)` + `siguiente_agente(cola_id)`.
- API admin: `GET/POST /colas`, `POST /colas/<id>/agentes`.

### FASE 19 — Supervisión
- Rol `supervisor` en `agentes`. Decorador `@requiere_rol('supervisor')`.
- Capacidades: ver TODAS las conversaciones, tomar, transferir, monitorear SLA,
  ver agentes conectados (presencia vía `agentes.ultimo_visto` + heartbeat JS),
  cerrar.
- **Dashboard dedicado** `/supervision` (template `supervision.html`).

### FASE 20 — Auditoría
- Tabla `auditoria`. Helper único `auditar(usuario, accion, conv_id, detalle)`
  llamado desde: inicio/fin atención, transferencias, validaciones, consultas de
  datos (cliente/cuentas/préstamos), descargas de archivos.
- API: `GET /auditoria?usuario&accion&desde&hasta` (sólo supervisor).

### FASE 21 — Base de conocimiento (KB)
- Tabla `kb_articulos`. Búsqueda rápida (LIKE; opcional SQLite FTS5).
- Integración con agente: insertar respuesta sugerida / copiar / **enviar**
  (reusa endpoint `/enviar`).
- APIs: `GET /kb?q=&categoria=`, `GET /kb/<id>`, panel lateral en modal.

### FASE 22 — Respuestas rápidas
- Tabla `respuestas_rapidas`. Render de variables `{{nombre}}`, `{{telefono}}`,
  `{{cod_persona}}` con el contexto de la conversación (server-side, simple
  `str.replace` controlado — NO Jinja sobre input de usuario).
- Categorías: Saludo, Despedida, Validación, Seguimiento, Cobros.
- API: `GET /respuestas-rapidas?categoria=`, dropdown en composer del modal.

### FASE 23 — Timeline 360
- Vista única que une por `cod_persona`/`telefono`: conversaciones, encuestas,
  notificaciones (Oracle `NOTIFICACIONES_CLIENTES` — reusa
  `buscar_notificaciones_por_destinos`), validaciones, adjuntos, transferencias.
- API: `GET /cliente/<cod_persona>/timeline`.
- UX: panel/tab "360" en el modal o vista `/cliente/<id>/360`.

### FASE 24 — Dashboard operacional
- KPIs: conversaciones activas/cerradas, tiempo promedio respuesta, SLA,
  agentes activos, conversaciones por canal.
- **Gráficas** (Chart.js vía CDN, sin build step).
- API: `GET /dashboard/kpis?desde&hasta` (agrega en SQLite).

### FASE 25 — IA para agentes
- Respuesta sugerida, resumen automático, detección de sentimiento, próxima
  mejor acción. Backend **DeepSeek/Ollama** (reusa cliente LLM existente).
- Cachear `resumen`/`sentimiento` en `conversaciones` para no recomputar.
- APIs: `POST /ia/sugerir`, `POST /ia/resumen/<conv_id>`,
  `POST /ia/sentimiento/<conv_id>`. Asíncrono/no bloqueante en UI.

### FASE 26 — Preparación multicanal
- Abstracción de canal ya parcialmente presente (`canal`, `canal_origen`).
- Definir interfaz `adaptador_canal` (enviar/normalizar entrante) para WhatsApp,
  Messenger, Instagram, Telegram, WebChat, SMS, Voz (Asterisk).
- Mantener **conversación unificada** por `cod_persona`/`telefono` a través de
  canales. Sólo preparación (interfaces + stubs), no integración completa.

---

## 3. APIs Flask (resumen de nuevos endpoints)

Asignación: `asignar`, `tomar`, `liberar`, `reasignar`.
Notas: `GET .../notas`. Transferencia: `POST .../transferir` (extendido).
SLA: `/sla/conversacion/<id>`, `/sla/resumen`. Etiquetas: `.../etiquetas` (CRUD),
`/etiquetas`. Colas: `/colas` (CRUD), `/colas/<id>/agentes`.
Supervisión: `/supervision`. Auditoría: `/auditoria`. KB: `/kb`, `/kb/<id>`.
Respuestas rápidas: `/respuestas-rapidas`. Timeline: `/cliente/<id>/timeline`.
KPIs: `/dashboard/kpis`. IA: `/ia/sugerir`, `/ia/resumen/<id>`,
`/ia/sentimiento/<id>`. Todas protegidas con sesión; las de supervisor con
`@requiere_rol('supervisor')`.

## 4. Componentes Jinja
`panel_notas.html`, `panel_etiquetas.html`, `panel_sla.html` (semáforo),
`panel_kb.html`, `panel_respuestas_rapidas.html`, `panel_timeline.html`,
`panel_ia.html`, `modal_transferencia.html`, `supervision.html`,
`dashboard_operacional.html`. Reusan `getJSON` y el patrón de carga del modal
actual.

## 5. JS requerido
- Extender el JS del modal: cargar notas/etiquetas/SLA/KB/respuestas/IA bajo
  demanda (lazy) con `getJSON`.
- Heartbeat de presencia (Fase 19): `POST /agentes/ping` cada ~30 s.
- Chart.js (CDN) para Fases 16/24.
- Selector de respuestas rápidas con sustitución de variables en cliente o
  server (preferible server por seguridad).

## 6. Flujo UX
1. Conversación entra → `NUEVA` → enruta a `EN_COLA` (Fase 18).
2. Agente la **toma** → `EN_ATENCION` (marca SLA primera respuesta).
3. Agente usa KB / respuestas rápidas / IA sugerida; agrega notas/etiquetas.
4. Si requiere otro depto → **transferencia** con motivo → `ESCALADA`/reasignada.
5. Resolución → **cerrar** → `CERRADA` (marca SLA resolución).
6. Supervisor monitorea en `/supervision`; todo queda en `auditoria`.

## 7. Riesgos
- Migraciones en producción: usar siempre `ADD COLUMN`/`CREATE IF NOT EXISTS`
  idempotente; nunca DROP. Backfill de `estado_workflow`.
- No romper entrega: los hooks de SLA/auditoría sólo **leen/registran**, no
  alteran el flujo de mensajes ni el handoff existente.
- Inyección en respuestas rápidas: sustituir variables con whitelist, NO
  renderizar Jinja sobre texto del agente/cliente.
- Carga Oracle: Timeline/360 debe reusar la consulta **por lote**
  (`buscar_notificaciones_por_destinos`) — no consultar por fila.
- IA (Fase 25): latencia/costos → asíncrono + caché; degradar elegante si el
  LLM no responde.
- Concurrencia SQLite: escrituras de auditoría/asignación cortas y con commit;
  considerar WAL si sube la contención.

## 8. Plan de pruebas
- Unit: máquina de estados (transiciones válidas/ inválidas), router de colas
  (round robin/prioridad), render de variables de respuestas rápidas, semáforo
  SLA (límites verde/amarillo/rojo).
- Integración: asignar→tomar→transferir→cerrar deja filas correctas en
  `asignaciones`, `transferencias`, `auditoria`, `sla_eventos`.
- Permisos: endpoints de supervisor rechazan rol agente.
- Regresión: handoff Bot/Humano, OTP, validación y CSV siguen funcionando.
- Migración: correr `crear_db()` sobre copia de DB de producción sin errores.

## 9. Orden recomendado de implementación
1. **Fase 13** (estados + asignación) — base del resto.
2. **Fase 20** (auditoría) — transversal, instrumentar desde temprano.
3. **Fase 14** (notas) y **Fase 15** (transferencia) — completar lo parcial.
4. **Fase 17** (etiquetas) — barato y habilita filtros.
5. **Fase 16** (SLA) — necesita marcas de tiempo ya capturándose.
6. **Fase 18** (colas) — sobre estados + agentes.
7. **Fase 19** (supervisión) — sobre estados/SLA/colas.
8. **Fase 22** (respuestas rápidas) y **Fase 21** (KB) — productividad agente.
9. **Fase 23** (timeline 360) y **Fase 24** (dashboard operacional) — vistas.
10. **Fase 25** (IA) — sobre datos ya estructurados.
11. **Fase 26** (multicanal) — preparación final.

---

## Seguimiento de estado

| Fase | Tema | Estado |
|------|------|--------|
| 13 | Asignación de agentes | 🟡 parcial (cols/funcs base existen; falta máquina de estados + tomar/liberar/UI) |
| 14 | Notas internas | 🟡 parcial (backend NOTE listo; falta panel UI + GET) |
| 15 | Transferencia | 🟡 parcial (reasigna; falta depto/motivo/historial) |
| 16 | SLA | 🔴 pendiente |
| 17 | Etiquetas | 🔴 pendiente |
| 18 | Colas | 🔴 pendiente |
| 19 | Supervisión | 🔴 pendiente |
| 20 | Auditoría | 🔴 pendiente |
| 21 | Base de conocimiento | 🔴 pendiente |
| 22 | Respuestas rápidas | 🔴 pendiente |
| 23 | Timeline 360 | 🔴 pendiente |
| 24 | Dashboard operacional | 🔴 pendiente |
| 25 | IA para agentes | 🔴 pendiente |
| 26 | Preparación multicanal | 🟡 base (`canal`/`canal_origen` existen) |
