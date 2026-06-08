#!/usr/bin/env python3

import sqlite3
import json

DB = "chatbot.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

cur = conn.cursor()

print("=======================================")
print("Migrando interacciones_chatbot")
print("=======================================")

#
# Crear mapa de conversaciones
#
map_conv = {}

cur.execute("""
    SELECT
        session_id,
        MAX(canal) canal,
        MAX(cod_persona) cod_persona,
        MIN(fecha_hora) fecha_inicio,
        MAX(fecha_hora) fecha_fin
    FROM interacciones_chatbot
    GROUP BY session_id
""")

sesiones = cur.fetchall()

print(f"Sesiones encontradas: {len(sesiones)}")

for row in sesiones:

    session_id = row["session_id"]

    cur.execute("""
        INSERT INTO conversaciones (
            session_id,
            canal,
            canal_origen,
            cod_persona,
            estado,
            fecha_creacion,
            fecha_ultimo_mensaje
        )
        VALUES (
            ?, ?, ?, ?, 'ABIERTA', ?, ?
        )
    """, (
        session_id,
        row["canal"],
        row["canal"],
        row["cod_persona"],
        row["fecha_inicio"],
        row["fecha_fin"]
    ))

    map_conv[session_id] = cur.lastrowid

conn.commit()

print(f"Conversaciones creadas: {len(map_conv)}")

#
# Migrar mensajes
#
cur.execute("""
    SELECT *
    FROM interacciones_chatbot
    ORDER BY fecha_hora ASC, id ASC
""")

rows = cur.fetchall()

print(f"Interacciones encontradas: {len(rows)}")

total_mensajes = 0

for row in rows:

    conversacion_id = map_conv[row["session_id"]]

    metadata = {}

    #
    # Intent Source
    #
    if row["intent_source"]:
        metadata["intent_source"] = row["intent_source"]

    #
    # Intención
    #
    template_id = None

    if row["intencion"]:

        try:
            intent = json.loads(row["intencion"])

            metadata["intencion"] = intent

            if isinstance(intent, dict):
                template_id = intent.get("templateId")

        except Exception:
            metadata["intencion_raw"] = row["intencion"]

    #
    # Pregunta -> Mensaje IN
    #
    if row["pregunta"] and row["pregunta"].strip():

        cur.execute("""
            INSERT INTO mensajes (
                conversacion_id,
                direccion,
                canal,
                contenido,
                template_id,
                metadata,
                fecha_hora
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            conversacion_id,
            "IN",
            row["canal"],
            row["pregunta"],
            template_id,
            json.dumps(metadata, ensure_ascii=False),
            row["fecha_hora"]
        ))

        total_mensajes += 1

    #
    # Respuesta -> Mensaje OUT
    #
    if row["respuesta"] and row["respuesta"].strip():

        cur.execute("""
            INSERT INTO mensajes (
                conversacion_id,
                direccion,
                canal,
                contenido,
                template_id,
                metadata,
                fecha_hora
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            conversacion_id,
            "OUT",
            row["canal"],
            row["respuesta"],
            template_id,
            json.dumps(metadata, ensure_ascii=False),
            row["fecha_hora"]
        ))

        total_mensajes += 1

conn.commit()

print(f"Mensajes creados: {total_mensajes}")

#
# Verificación
#
cur.execute("SELECT COUNT(*) FROM conversaciones")
total_conv = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM mensajes")
total_msg = cur.fetchone()[0]

print("")
print("=======================================")
print("Resumen")
print("=======================================")
print(f"Conversaciones : {total_conv}")
print(f"Mensajes       : {total_msg}")
print("=======================================")

conn.close()

print("Migración finalizada")
