#!/opt/rag/bin/python
from flask import Flask, request, jsonify, send_from_directory, session, request
from flask_session import Session
import uuid
from llm_helper import process_query, preguntar_llm, detectar_intencion
from plantillas_prompt import conocimiento_general
from rag_db import disable_log, enable_log, envia_sms, buscar_cliente_por_cedula, contexto_cliente, contexto_agencias, fin, logg, validar_cedula
import requests
from threading import Thread
import time
import json
from random import randint
from conversation import ConversationManager

redisdb = ConversationManager("0")
app = Flask(__name__)
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redisdb.getRedis()
app.config["SESSION_PERMANENT"] = False
Session(app)
# Guardar OTP y Cliente
otps = {}
ultpreg = {}
OLLAMA_URL = "http://localhost:11434/api/generate"
#OLLAMA_MODEL = "mistral:7b-instruct"
OLLAMA_MODEL = "mistral-tuned"
MISTRAL_KEY = "kAWpgcRmXj0jNyVOSX9JPsPsgQmvqq48"

ZENVIA_TOKEN = "lPJliG5RIz0q3dN0iiplWgiPy6q1S7PtAyhz"
ZENVIA_NUMBER = "18097220802"
ZENVIA_HEADERS = {
    "X-API-TOKEN": ZENVIA_TOKEN,
    "Content-Type": "application/json"
}
# Ruta que no quieres loguear
RUTAS_IGNORADAS = ['/', '/webchat/mensajes']

@app.before_request
def filter_logs():
    if request.path in RUTAS_IGNORADAS:
        # Desactiva el logging para esta petición
        disable_log()

@app.before_request
def ensure_session_id():
    sid = "0"
    if 'session_id' not in session:
        sid = str(uuid.uuid4())
        session['session_id'] = sid
    logg(f"Session: {sid}")

@app.after_request
def reenable_logger(response):
    enable_log()
    return response

@app.route("/")
def home():
    return send_from_directory("static", "webchat.html")

@app.route("/loferia.jpg")
def loferia():
    return send_from_directory("static", "loferia.jpg")

@app.route('/webhook/zenvia', methods=['POST'])
def zenvia_webhook():
    data = request.json
    logg(f"Mensaje recibido de Zenvia: {data}")
    # 1. Filtrado robusto de mensajes
    if data.get("direction") != "IN" or not data.get("message"):
        return jsonify({"status": "ignored"}), 200
    
    # 2. Ignorar mensajes duplicados o propios
    message_id = data["message"].get("id")
    if message_id and message_id == session.get("last_processed_msg"):
        return jsonify({"status": "duplicate"}), 200
    
    # 3. Extraer datos seguros
    try:
        mensaje = data["message"]["contents"][0].get("text", "")
        mensaje = mensaje.strip()
        numero = data["message"]["from"]
    except (KeyError, IndexError):
        return jsonify({"status": "invalid_format"}), 400
    
    # 4. Procesamiento condicional
    if not mensaje.strip():
        return jsonify({"status": "empty_message"}), 200
    
    # 5. Guardar ID para evitar reprocesamiento
    session["last_processed_msg"] = message_id
    logg(f"zenvia_webhook: Procesando: {numero}: {mensaje}")
    # 6. Lógica de negocio        
    Thread(target=procesar, args=(numero, mensaje, "wa", message_id)).start()

    # 7. Respuesta inmediata para evitar timeout
    return jsonify({"status": "processing"}), 200
    #return jsonify({"status": "ok"}), 200

@app.route("/webchat/mensajes")
def mensajes_webchat():
    session_id = session.get("session_id")
    mensajes = redisdb.get_messages(session_id)
    return jsonify({"mensajes": mensajes})

@app.route("/chat", methods=["POST"])
def web_chat():
    data = request.get_json()
    mensaje = data.get("message", "")
    cliente_id = data.get("cliente_id", "")
    logg(f"web_chat: Recibi: '{mensaje}'")     

    if not mensaje:
        return jsonify({"error": "Falta el campo 'pregunta'"}), 400
    session_id = session.get("session_id")
    
    Thread(target=procesar, args=(session_id, mensaje, "wc", None)).start()

    # 7. Respuesta inmediata para evitar timeout
    return jsonify({"status": "processing"}), 200

def procesar(numero, mensaje, canal, message_id):
        logg(f"procesar:\t\nnumero: {numero},\t\nmensaje: {mensaje},\t\ncanal: {canal},\t\nmessage_id: {message_id}")
        estado = redisdb.get_variable(numero, "estado_validacion")
        mensaje_original = mensaje.strip()        
        # --- 1. Si está esperando cédula ---
        if estado == b"esperando_cedula":
            valida, mensaje = validar_cedula(mensaje_original)
            valida = True
            if valida:
                row = buscar_cliente_por_cedula(mensaje_original)
                if row:
                    cliente_id = row["cod_persona"]
                    nombres = row["nombres"]
                    sexo = row["sexo"]
                    if sexo == "M":
                        saludo = "Bienvenido"
                    if sexo == "F":
                        saludo = "Bienvenida"
                    redisdb.set_variable(numero, "cliente_id", cliente_id)
                    redisdb.set_variable(numero, "estado_validacion", "esperando_otp")
                    redisdb.set_variable(numero, "nombres", row["nombres"])
                    # Generar OTP
                    otp = str(randint(100000, 999999))
                    redisdb.set_variable(numero, "otp", otp, expira=300)
                    logg(f"OTP generado para {cliente_id}: {otp}")
                    sms = f"Este es el OTP generado para validar tu identidad y poder consultar tus productos en Real[IA]: {otp}"
                    pid, celular = envia_sms(cliente_id, sms)       
                    cel4d = celular[-4:]
                    if pid > 0:
                        mensaje = f"!{saludo} {nombres}! Te he enviado un código de verificación OTP a su celular terminado en {cel4d}. Por favor ingrese el OTP que recibió."            
                        
                    else:
                        mensaje = f"No fue posibble enviar un código de verificación OTP a su celular terminado en {cel4d}. Por favor pase por una sucursal a corregir sus datos."
                    respuesta = mensaje
                else:
                    respuesta = "❌ No encontramos un cliente con esa cédula. Por favor, verifícala."
            else:
                respuesta = (f"Cédula: {mensaje_original.ljust(15)} -> {'VÁLIDA' if valida else 'INVÁLIDA'}: {mensaje}")
                enviar_respuesta(canal, message_id, numero, respuesta)
                respuesta = "Por favor, ingresa tu número de cédula sin guiones para continuar."

        # --- 2. Si está esperando OTP ---
        elif estado == b"esperando_otp":
            otp_esperado = redisdb.get_variable(numero, "otp")
            if otp_esperado and mensaje_original == otp_esperado.decode():
                redisdb.set_variable(numero, "estado_validacion", "validado")
                redisdb.del_variable(numero, "otp")
                respuesta = "✅ Validación exitosa. Procesando tu solicitud..."
                enviar_respuesta(canal, message_id, numero, respuesta)
                # Ejecutar la intención original
                intencion = redisdb.get_variable(numero, "intencion_pendiente")
                pregunta_b = redisdb.get_variable(numero, "pregunta_original")
                pregunta = pregunta_b.decode()
                cliente_id = redisdb.get_variable(numero, "cliente_id")
                # Aqui evaluo si buscaré cuentas, certificados o prestamos o prestamos de feria            
                enviar_respuesta(canal, message_id, numero, "Espera mientras busco la información solicitada...")
                
                logg(f"procesar: pregunta {pregunta}")
                result = process_query(pregunta)
                contexto = contexto_cliente(cliente_id.decode(), result)
                respuesta = wa_llm(numero, intencion.decode(), pregunta.decode(), contexto)
            else:
                respuesta = "❌ OTP incorrecto. Intenta nuevamente."

        # --- 3. Si ya está validado ---
        elif estado == b"validado":
            cliente_id = redisdb.get_variable(numero, "cliente_id")
            #general, confidencial, intent, contexto = detectar_intencion(mensaje)
            result = process_query(mensaje)
            confidencial = (result["type"] == "personal")
            contexto = result["context"]
            intent = result["intent"]
            if confidencial and cliente_id:
                contexto = contexto_cliente(cliente_id.decode(), result)
                enviar_respuesta(canal, message_id, numero, "Espera mientras busco la información solicitada...")
                respuesta = wa_llm(numero, intent, mensaje, contexto)
            else:
                enviar_respuesta(canal, message_id, numero, "Espera mientras busco la información solicitada...")
                respuesta = wa_llm(numero, intent, mensaje, contexto)

        # --- 4. Primer mensaje: detectar intención confidencial ---
        else:
            general, confidencial, intent, contexto = detectar_intencion(mensaje)
            if confidencial:
                redisdb.set_variable(numero, "estado_validacion", "esperando_cedula")
                redisdb.set_variable(numero, "intencion_pendiente", intent)
                redisdb.set_variable(numero, "pregunta_original", mensaje)
                respuesta = "🔐 Para darte esa información, necesito validar tu identidad. Por favor escribe tu número de cédula."
            else:
                respuesta = wa_llm(numero, intent, mensaje, contexto)        
        enviar_respuesta(canal, message_id, numero, respuesta)
        

def enviar_respuesta(canal, message_id, numero, respuesta):
    if canal == "wa":
            enviar_respuesta_wa(message_id, numero, respuesta)
    elif canal == "wc":
        enviar_respuesta_web(numero, respuesta)

def enviar_respuesta_wa(idRef, telefono, texto):
    max_chars = 4000
    partes = []
    while len(texto) > max_chars:
        corte = texto.rfind(" ", 0, max_chars)
        if corte == -1: corte = max_chars
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip()
    partes.append(texto)
    
    for parte in partes:
        payload = {
            "externalId": "realia",
            "from": ZENVIA_NUMBER,
            "to": telefono,
            "idRef" : idRef,
            "contents": [
                {
                    "type": "text",
                    "text": parte
                }
            ]
        }
        response = requests.post("https://api.zenvia.com/v2/channels/whatsapp/messages", json=payload, headers=ZENVIA_HEADERS, verify=False)
        logg(f"Respuesta de Zenvia: {response.status_code}, {response.text}")

def enviar_respuesta_web(session_id, respuesta):
    redisdb.add_message(session_id, respuesta)

def llamada_llm(session_id, intencion, pregunta, contexto):   
    try:
        logg(f"llamada_llm: Inicio '{intencion}' '{pregunta}'\r\n{contexto}")
        inicio = time.time()        
        chat = ConversationManager(session_id)        
        conocimiento_extra = chat.get_conversation_history()        
        #if intencion == 'producto':
        #    respuesta = ""
            #for l in contexto:
            #    respuesta += f"\n- {l['nombre']}: {l['contenido']}"
            # respuesta
        contexto_str = json.dumps(contexto, ensure_ascii=False)
        logg(f"llamada_llm: Inicio 4 {contexto_str}")
        respuesta = preguntar_llm(intencion, pregunta, contexto_str, conocimiento_extra, max_reintentos=2, modelo=OLLAMA_MODEL, endpoint=OLLAMA_URL)
        logg(f"llamada_llm: Inicio 5")
        respuesta = respuesta.strip()
        logg(f"llamada_llm: Inicio 6")
        chat.add_user_message(pregunta)
        logg(f"llamada_llm: Inicio 7")
        chat.add_assistant_message(respuesta)
        logg(f"llamada_llm: Inicio 8")
        fin_ = fin(inicio)
        logg(f"llamada_llm: Resultado tiempo {fin_}")
        return respuesta
        if intencion == 'direccion':
            if contexto:
                c = 0
                for suc in contexto:
                    c += 1
                    if len(contexto) == 1 :
                        if {suc['nombre']} == "Central":
                            respuesta = f"La {suc['nombre']} se encuentra en la {suc['direccion']}. Puedes contactarla al número {', '.join(suc['telefonos'])}. Las extensiones son {', '.join(suc['extensiones'])}. Recuerda que la sucursal está abierta de {', '.join(suc['horario'])}."    
                        else:
                            respuesta = f"La sucursal de {suc['nombre']} se encuentra en la {suc['direccion']}. Puedes contactarla al número {', '.join(suc['telefonos'])}. Las extensiones son {', '.join(suc['extensiones'])}. Recuerda que la sucursal está abierta de {', '.join(suc['horario'])}."
                    else:
                        if c == 1 :
                           respuesta = "Listado de sucursales:\n"
                        respuesta += f"\n- {suc['nombre']}: {suc['direccion']}. Tel: {', '.join(suc['telefonos'])}."
                return respuesta
        elif intencion == 'asociado':
            if contexto:
                for req in contexto:
                    #respuesta = f"Para ser un asociado de Vega Real debes: \r\n - {', '.join(req['requisitos'])}."
                    respuesta = "Para ser un asociado de Vega Real debes:\n" + "\n".join(f"- {req}" for req in contexto['requisitos'])
                    respuesta += "\n\nSi quieres saber cuál es la sucursal más cercana, puedes preguntarme las direcciones de las sucursales."
                    return respuesta
        elif intencion == 'capacidades':
            conocimiento_extra = conocimiento_general(None)
        respuesta = preguntar_llm(intencion, pregunta, contexto, conocimiento_extra, max_reintentos=2, modelo=OLLAMA_MODEL, endpoint=OLLAMA_URL)
        respuesta = respuesta.strip()
        chat.add_user_message(pregunta)
        chat.add_assistant_message(respuesta)
        fin_ = fin(inicio)
        logg(f"llamada_llm: Resultado tiempo {fin_}")
        return respuesta
        
    except Exception as e:
        logg(f"llamada_llm: excepción: {e}")
        return "Estamos presentando inconvenientes, por favor intenta en unos minutos"

def request_llm(intencion, pregunta, contexto, requiere_validacion):   
    try:
        session_id = session['session_id']
        respuesta = llamada_llm(session_id, intencion, pregunta, contexto)
        return jsonify({"respuesta": respuesta, "requiere_validacion" : requiere_validacion})
        
    except Exception as e:
        logg(f"request_llm: excepción: {e}")
        return jsonify({"error": "Estamos presentando inconvenientes, por favor intenta en unos minutos"}), 500

def wa_llm(session_id, intencion, pregunta, contexto):   
    try:
        respuesta = llamada_llm(session_id, intencion, pregunta, contexto)
        return respuesta
        
    except Exception as e:
        logg(f"wa_llm: excepción: {e}")
        return "Estamos presentando inconvenientes, por favor intenta en unos minutos"

def prueba():
    numero = "18296966336"
    cliente_id = "37710"
    mensaje_original = "123456"
    redisdb.set_variable(numero, "cliente_id", cliente_id)
    redisdb.set_variable(numero, "estado_validacion", "validado")
    redisdb.set_variable(numero, "nombres", "Jose A. de la Cruz Malena")    
    procesar(numero, "cual es la cuota de mi gerencial?", "wc", cliente_id)
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)