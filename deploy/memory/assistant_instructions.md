Archivo de instrucciones para el asistente (GPT)

Última actualización: 2026-05-14

Propósito

Este documento explica cómo interactuar con el asistente que colabora en este repositorio. Contiene pautas sobre el tipo de peticiones que puede atender, el formato recomendado, seguridad mínima y ejemplos prácticos para tareas comunes (editar código, investigar errores, ejecutar comprobaciones rápidas).

Reglas rápidas

- Sé concreto y directo: indica qué archivo o funcionalidad quieres modificar o inspeccionar.
- Si pides cambios en el código, proporciona el objetivo y cualquier restricción (compatibilidad, versiones, tests obligatorios).
- Cuando corresponda, solicita que el asistente ejecute las comprobaciones (build/tests) y entregue un resumen PASS/FAIL.
- El asistente no hará cambios fuera del repositorio a menos que se le pida explícitamente y se expliquen los riesgos.

Formato recomendado para peticiones

1) Título claro: "Añadir validación X en archivo Y" o "Investigar por qué Z falla".
2) Objetivo: 1-2 frases con lo que hay que lograr.
3) Contexto opcional: logs, errores, screenshots o fragmentos del archivo.
4) Restricciones/Preferencias: p. ej. "no cambiar interfaz pública", "usar sqlite3", "añadir tests pytest".
5) Resultado esperado: cómo sabremos que la tarea se cumplió (ej: tests verdes, query SQL devuelve N filas, mensaje en logs).

Ejemplo de petición (ideal):

- Título: "Rechazar archivos entrantes por WhatsApp"
- Objetivo: "Cuando Zenvia entregue un mensaje con type!='text', responder que no aceptamos archivos y enviar el menú raíz."
- Contexto: pegar ejemplo de webhook (JSON) si es posible.
- Restricciones: "Cambiar solo `ragapi/app/api_llm.py` y no romper otros canales".
- Resultado esperado: "Respuesta enviada y registro en logs; la función `procesar` no recibe el contenido de archivo".

Cómo pide el asistente cambios y verificaciones

- El asistente propondrá un plan corto y aplicará cambios en el repo usando parches (VCS). Cada cambio incluirá:
  - Archivos modificados
  - Motivación breve
  - Cómo verificar localmente (comandos o tests)
- Después de aplicar cambios, el asistente intentará ejecutar tests rápidos o una comprobación de sintaxis. Informará si algo falla y propondrá correcciones.

Comandos útiles que el asistente puede ejecutar (si el usuario lo autoriza)

- Ejecutar tests unitarios (pytest):
  - pytest -q
- Consultar SQLite dentro del contenedor (ejemplo):
  - docker compose exec ragapi sqlite3 /opt/rag/app/chatbot.db ".tables"
- Reiniciar servicios (ejemplo):
  - docker compose restart ragapi

Seguridad y datos sensibles

- El asistente no exfiltrará secretos ni claves. Si se debe usar una credencial para pruebas, pásala manualmente o monta un entorno seguro.
- Evitar incluir secretos completos en los mensajes. Si aparece uno por accidente, indica al asistente que lo omita.

Comunicación y estilo de cambios

- El asistente usará un estilo conciso y directo en los commits/parches.
- Priorizará compatibilidad con el estilo ya presente en el repositorio.
- Preguntará antes de hacer cambios riesgosos (migraciones grandes, cambios de dependencias).

Ejemplos de solicitudes que el asistente puede atender

- "Añade logging cuando `guardar_interaccion` falle y vuelve 200 al webhook." (cambio en rag_db.py y api_llm.py)
- "Crea un script para volcar las últimas 50 interacciones en JSON." (nuevo archivo en tools/)
- "Implementa un endpoint protegido /admin/interacciones que devuelva las últimas N filas." (nueva ruta + control de acceso)

Contacto y responsabilidad

- El asistente automatiza tareas de desarrollo y pruebas; la responsabilidad final de revisar y desplegar cambios recae en el equipo.
- Siempre probar en un entorno de staging antes de desplegar a producción.

Registro de operaciones del asistente

- Cada vez que el asistente modifique el repositorio, añadirá una entrada al `memory/assistant_memory.md` indicando la fecha, los archivos cambiados y la verificación realizada.


Fin del archivo

Si quieres, añado un checklist de permisos (ejecutar comandos en contenedores, reiniciar servicios) que permita al asistente actuar más autónomamente cuando lo autorices explícitamente.
