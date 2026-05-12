from rag_db import contexto_cliente, fin, logg
import requests
import time

# ID de prueba (debe existir en Oracle)
cliente_id = "37710"  # reemplaza con un ID real de prueba
logg(f"Inicio prueba con cliente {cliente_id}")
# Paso 1: Obtener contexto desde Oracle
contexto = contexto_cliente(cliente_id)
print("=== CONTEXTO ===")
print(contexto)
print("\n================\n")

# Paso 2: Formar la pregunta
pregunta = "según este contexto ¿Cuál es el balance de mis cuentas excluyendo préstamos? ¿Cuáles son mis préstamos activos?"
# Paso 3: Enviar a Ollama (Mistral)
payload = {
    "model": "mistral:7b-instruct",
    "prompt" : f"""Eres un asistente virtual de Cooperativa Vega Real.
Usa el siguiente contexto para responder la pregunta del asociado. Si no sabes la respuesta, responde: "No tengo esa información."

Contexto:
{contexto}

Pregunta:
{pregunta}

Respuesta:""",
    "stream": False
}
inicio = time.time()
response = requests.post("http://localhost:11434/api/generate", json=payload)

# Paso 4: Mostrar respuesta
if response.ok:
    respuesta = response.json()["response"]
    print("=== RESPUESTA DE DEEPSEEK ===")
    print(respuesta)
else:
    print("Error en la consulta:", response.status_code, response.text)
logg("Listo!. Tiempo de procesamiento: " + fin(inicio))