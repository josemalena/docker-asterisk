#!/opt/rag/bin/python
from api_llm import process_query, fecha_de_texto, construir_prompt

intencion = "sucursal"
contexto = {"tipo": "actividad", "subtipo":"evento","fecha": "2025-05-17", "hora": "09:00 am", "contenido": "Sesión Conjunta de los Consejos de Administración y Vigilancia", "modalidad": "Presencial", "lugar": "Salón de Conferencia Casa Club"}
conocimiento_extra = ""
pregunta = "como puedo reclamar un articulo que no me llego de feria?"
#result = construir_prompt("saldo", pregunta, contexto, conocimiento_extra)
#result = fecha_de_texto(pregunta)
result = process_query(pregunta)

print(f"procesar: process_query -> {result}")
intent = result["intent"]
contexto = result["context"]
tipo = result["type"]
respuesta = ""
print(f"tipo = '{tipo}'")
try:
    descripcion = contexto[0]["descripcion"]
except:
    descripcion = None
if tipo == 'general':
    tipo_ = contexto[0]["tipo"]
    subtipo = contexto[0]["subtipo"]
    print(f"subtipo = {subtipo}")
    if subtipo in ["historia", "filosofia", "politica", "asociado", "estructura"]:
        tipo = 'ayuda'

if tipo == 'personal':

    respuesta = "🔐 Para darte esa información, necesito validar tu identidad. Por favor escribe tu número de cédula."
elif tipo == 'ayuda':
    respuesta = contexto[0]["contenido"]
    if descripcion:
        respuesta = descripcion + " " + respuesta

print(f"respuesta = {respuesta}")