Actúa como un Arquitecto de Software Senior especializado en Contact Centers Omnicanal, CRM, WhatsApp Business API, Messenger, Instagram, Telegram, SMS, Email y plataformas SaaS multiempresa.

Necesito diseñar e implementar un módulo completo de Atención al Cliente para mi plataforma RealIA.

Objetivo:

Permitir que conversaciones iniciadas por IA puedan ser transferidas a oficiales humanos y que dichos oficiales continúen la conversación desde una bandeja unificada.

Stack tecnológico:

* Backend: Python Flask
* Base de datos transaccional: PostgreSQL 17
* Oracle 11g para integración bancaria y datos core
* Redis para sesiones y estado temporal
* Frontend: HTML + Bootstrap + JavaScript
* WhatsApp vía Zenvia
* WebChat propio
* Arquitectura multiempresa
* PostgreSQL como repositorio principal de conversaciones
* Redis únicamente para estado temporal y cache

Requisitos arquitectónicos obligatorios:

* Multiempresa mediante empresa_id en todas las tablas.
* PostgreSQL debe ser el repositorio oficial de:

  * Conversaciones
  * Mensajes
  * Tickets
  * Asignaciones
  * SLA
  * Encuestas
  * Contact Center
  * Auditoría
  * Integraciones IA
* Oracle seguirá siendo la fuente oficial para:

  * Clientes
  * Cuentas
  * Préstamos
  * Certificados
  * ATM
  * Datos financieros
* Redis solamente para:

  * Sesiones
  * OTP
  * Estados temporales
  * Cache

1. Modelo de negocio

Explica detalladamente:

* Conversación
* Cliente
* Contacto
* Canal
* Agente
* Supervisor
* Cola
* SLA
* Ticket
* Prioridad
* Etiqueta
* Transferencia
* Escalamiento
* Cierre
* Reapertura
* IA
* Oficial humano

2. Arquitectura empresarial

Diseña una arquitectura enterprise con:

* RealIA
* Motor IA
* PostgreSQL
* Redis
* Oracle
* Contact Center
* Bandeja de agentes
* API REST
* WhatsApp
* Messenger
* Instagram
* Telegram
* SMS
* Email
* WebChat

Genera diagramas Mermaid.

3. Modelo de datos PostgreSQL

Diseña y genera scripts completos para PostgreSQL 17.

Tablas mínimas:

crm_empresas

crm_clientes

crm_contactos

crm_conversaciones

crm_mensajes

crm_colas

crm_agentes

crm_asignaciones

crm_transferencias

crm_notas

crm_etiquetas

crm_conversacion_etiqueta

crm_tickets

crm_sla

crm_auditoria

Todos los scripts deben incluir:

* PRIMARY KEY
* FOREIGN KEY
* CHECK
* UNIQUE
* INDEX
* PARTIAL INDEX
* GIN INDEX
* JSONB
* TRIGGERS
* FUNCTIONS
* VIEWS

4. Conversaciones

Implementa el concepto:

Una conversación pertenece al cliente y no al canal.

Ejemplo:

Cliente
→ WhatsApp

Cliente
→ Instagram

Cliente
→ Messenger

Cliente
→ WebChat

Todo debe consolidarse dentro de una sola conversación.

Diseña algoritmo de correlación omnicanal.

5. Modelo de mensajes

Diseña tabla de mensajes capaz de almacenar:

* WhatsApp
* Messenger
* Instagram
* Telegram
* SMS
* Email
* WebChat

Debe soportar:

* Texto
* Audio
* Imagen
* Video
* Documento
* Ubicación
* Reacciones
* Botones
* Plantillas

Usar JSONB para payloads.

6. Integración WhatsApp

Diseña soporte para:

* Zenvia
* Meta Cloud API
* Twilio
* Infobip

Guardar:

* provider_message_id
* provider_conversation_id
* provider_contact_id
* template_id
* template_fields
* webhook_payload

Usar JSONB.

7. Gestión de conversaciones

Implementa reglas:

Si existe conversación abierta:

* reutilizar conversación

Si está cerrada hace menos de 72 horas:

* reabrir conversación

Si está cerrada hace más de 72 horas:

* crear conversación nueva

Genera funciones PostgreSQL para esto.

8. Motor de asignación

Implementa:

* Round Robin
* Menor carga
* Especialidad
* Supervisor
* Manual

Genera:

* algoritmo
* pseudocódigo
* implementación Python

9. Transferencia IA → Humano

Diseña flujo completo:

Cliente
→ IA

IA resuelve
→ cerrar

IA no resuelve
→ crear ticket
→ asignar oficial

Oficial atiende
→ resolver

Oficial devuelve a IA
→ continuar automatización

Implementa máquina de estados completa.

10. Bandeja de agentes

Diseña UI enterprise.

Vistas:

* Mis conversaciones
* Pendientes
* Sin asignar
* SLA vencidos
* Escalados
* Cerrados

Filtros:

* Empresa
* Canal
* Fecha
* Estado
* Prioridad
* Agente
* Etiqueta

Genera wireframes ASCII.

11. API REST Flask

Genera endpoints:

GET /api/conversations

GET /api/conversations/{id}

POST /api/conversations

POST /api/conversations/{id}/assign

POST /api/conversations/{id}/transfer

POST /api/conversations/{id}/close

POST /api/conversations/{id}/reopen

POST /api/conversations/{id}/message

POST /api/conversations/{id}/note

POST /api/conversations/{id}/tag

POST /api/conversations/{id}/escalate

GET /api/queues

GET /api/agents

Incluye ejemplos JSON.

12. PostgreSQL avanzado

Aprovecha características nativas:

* JSONB
* GIN Index
* Full Text Search
* Generated Columns
* Materialized Views
* Triggers
* Stored Procedures
* Partitioning por fecha
* Auditoría automática

Genera ejemplos completos.

13. Analítica

Diseña dashboards para:

* Conversaciones abiertas
* Tiempo promedio de respuesta
* SLA
* Productividad por agente
* Canales más utilizados
* Intenciones más frecuentes
* Conversaciones resueltas por IA
* Conversaciones escaladas

Genera consultas SQL.

14. Seguridad

Implementa:

* Multiempresa obligatorio
* RBAC
* Auditoría completa
* Historial inmutable
* Soft Delete
* JWT
* Registro de acceso

Roles:

* Agente
* Supervisor
* Administrador
* Auditor

15. Rendimiento

Diseña para:

* 500 agentes simultáneos
* 100,000 conversaciones mensuales
* 10 millones de mensajes históricos
* 100 mensajes por segundo

Incluye:

* índices
* caché Redis
* particionamiento PostgreSQL
* estrategia de archivado

16. Integración con RealIA

Diseña integración completa con el sistema actual:

* Flask
* Redis
* WhatsApp Zenvia
* Oracle
* SQLite actual (como fuente de migración)

Genera plan de migración desde SQLite hacia PostgreSQL.

17. Entregables

Genera:

* Arquitectura completa
* Diagramas Mermaid
* Modelo ER
* Scripts PostgreSQL
* Código Flask
* Servicios
* APIs
* Estructura de carpetas
* Wireframes
* Estrategia de despliegue Docker
* Plan de migración desde SQLite

La solución debe estar lista para producción, orientada a una cooperativa financiera, siguiendo principios enterprise, omnicanal, multiempresa y escalable a largo plazo.
