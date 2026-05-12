#!/opt/rag/bin/python
import requests
import uuid
import time
import json
import re
import os
import logging
import urllib3
#from openai import OpenAI
from typing import Dict, List, Optional
from flask import Flask, request, jsonify, send_from_directory, session, request, redirect, url_for, render_template_string, flash, abort
from flask_session import Session
from pywebpush import webpush, WebPushException
from threading import Thread
from datetime import datetime, timedelta
from random import randint

# Base de datos
from rag_db import ConversationManager, obtener_interacciones, guardar_interaccion, disable_log, enable_log, envia_sms, buscar_cliente_por_cedula, buscar_cliente, contexto_cliente, fin, logg, loge, logx, validar_cedula

# Menú interactivo WhatsApp
import menu

# Parcho para evitar advertencias desde el Fortigate:
urllib3.disable_warnings()

##
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) 

redisdb = ConversationManager("0")
app = Flask(__name__)
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redisdb.getRedis()
app.config["SESSION_PERMANENT"] = False
Session(app)
# Guardar OTP y Cliente
otps = {}
ultpreg = {}

OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

#client = OpenAI( api_key=OPENAI_API_KEY)

#OLLAMA_URL = "http://ollama:11434/api/generate"
#OLLAMA_MODEL = "mistral-tuned"
#OLLAMA_MODEL = "mistral:7b-instruct"

#OLLAMA_URL = "http://tts.vegareal.local/api/generate"
#OLLAMA_MODEL = "deepseek-llm:7b-chat-q5_K_M"


# VAPID keys generadas (puedes generar las tuyas con 'npx web-push generate-vapid-keys')
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {"sub": "mailto:" + os.getenv("VAPID_CLAIMS")}

BASE_PATH = os.getenv("BASE_PATH")


MISTRAL_KEY = "kAWpgcRmXj0jNyVOSX9JPsPsgQmvqq48"

# Zenvia WhatsApp 
ZENVIA_API = os.getenv("ZENVIA_API") #"https://api.zenvia.com/v2/channels/whatsapp/messages"
ZENVIA_TOKEN = os.getenv("ZENVIA_TOKEN") #"lPJliG5RIz0q3dN0iiplWgiPy6q1S7PtAyhz"
ZENVIA_WANUMBER = os.getenv("ZENVIA_WANUMBER") #"18097220802"
ZENVIA_HEADERS = {
    "X-API-TOKEN": ZENVIA_TOKEN,
    "Content-Type": "application/json"
}

DIAS_SEMANA = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6
}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

# Ruta que no quieres loguear
RUTAS_IGNORADAS = ['/', '/webchat/mensajes']

def getClientInfo(request):
    client_info = {
        'timestamp': datetime.now().isoformat(),
        'request': {
            'method': request.method,
            'url': request.url,
            'headers': dict(request.headers),
            'args': dict(request.args),
            'form': dict(request.form) if request.form else None,
            'json': request.get_json(silent=True),  # Manejo más seguro de JSON
            'cookies': dict(request.cookies),
            'remote_addr': request.remote_addr,
            'user_agent': str(request.user_agent)
        }
    }
    return client_info

@app.route("/")
def home():
    session_id = session.get("session_id", str(uuid.uuid4()))
    session["session_id"] = session_id

    with open(os.path.join(BASE_PATH, "static", "webchat.html"), "r", encoding="utf-8") as f:
        html_content = f.read()

    # Inserta la constante al inicio del <script>
    html_content = html_content.replace(
        "<session>",
        f"<script>\nconst session_id = '{session_id}';</script>"
    )

    response = app.response_class(html_content, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    client_info = getClientInfo(request)
    logg(f"New session_id '{session_id}': {client_info}")
    return response
### imagenes
@app.route("/icons/<filename>")
def serve_icon(filename):
    allowed_files = ["icon-512x512.png", "icon-192x192.png", "icon-96x96.png", "loferia.jpg", "favicon32x32.png", "instruccion-ios.png"]
    if filename in allowed_files:
        return send_from_directory("static", filename)
    else:
        abort(404)
### 
### Scripts
@app.route("/pwa/<filename>")
def get_script(filename):

    allowed_files = ["manifest.json", "push.json", "sw.js", "webpush.js", "push.json", "push.html", "webchat.js", "webchat.html", "icon-192x192.png", "icon-512x512.png"]
    if filename in allowed_files:
        response = send_from_directory("static", filename)
    else:
        abort(404)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    logg(f"get_script: {filename}")
    return response
###

@app.route('/subscribe', methods=['POST'])
def subscribe():
    subscription_info = request.json
    session_id = session.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id requerido"}), 400
    logg(f"Nueva suscripción: '{session_id}' -> {subscription_info}")
    redisdb.set_subscription(session_id, subscription_info)
    set_browser_state(session_id, "1")
    return jsonify({"status": "subscribed"}), 201

@app.route('/push')
def push_status():
    session_id = request.args.get('session_id')
    active = request.args.get('active')
    estado = set_browser_state(session_id, active)
    return jsonify({"status": f"Sesión {session_id} marcada como {estado}"}), 200

@app.route('/vapid_public_key')
def vapid_public_key():
    session_id = session.get("session_id") 
    if not session_id:
        return jsonify({"error": "session_id requerido"}), 400
    logg(f"Enviando VAPID_PUBLIC_KEY a {session_id}")
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/webhook/zenvia', methods=['POST', 'GET'])
def zenvia_webhook():
    client_info = getClientInfo(request)
    logg(f"Webook - Request: {client_info}")
    if request.method != 'POST':
        return redirect(url_for('home'))
    data = request.json
    logg(f"Webook - Mensaje: {data}")
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
        payload = data["message"]["contents"][0].get("payload", "")
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
    Thread(target=procesar, args=(numero, mensaje, payload, "wa", message_id)).start()

    # 7. Respuesta inmediata para evitar timeout
    return jsonify({"status": "processing"}), 200
    #return jsonify({"status": "ok"}), 200

@app.route("/webchat/mensajes")
def mensajes_webchat():
    session_id = session.get("session_id")
    mensajes = redisdb.get_web_messages(session_id)
    return jsonify({"mensajes": mensajes})

@app.route("/chat", methods=["POST"])
def web_chat():
    data = request.get_json()
    mensaje = data.get("message", "")
    logg(f"web_chat: Recibi: '{mensaje}'")     

    if not mensaje:
        return jsonify({"error": "Falta el campo 'pregunta'"}), 400
    session_id = session.get("session_id")
    logg(f"web_chat: session_id: '{session_id}'")     
    message_id = str(uuid.uuid4())
    
    Thread(target=procesar, args=(session_id, mensaje, None, "wc", message_id)).start()

    # 7. Respuesta inmediata para evitar timeout
    return jsonify({"status": "processing", "message_id":message_id}), 200

def set_browser_state(session_id, active):
    redisdb.set_variable(session_id, "active", active)
    state = "activo" if active == "1" else "inactivo"
    logg(f"[{session_id}] Estado de visibilidad actualizado: {state}")
    return state

def procesar(numero, mensaje, payload, canal, message_id):
        result = None
        cod_persona = 0
        tipo = None
        logg(f"procesar(numero: {numero}, mensaje: '{mensaje}', canal: {canal}, message_id: {message_id})")
        estado = redisdb.get_variable(numero, "estado_validacion")
        logg(f"procesar: estado_validacion '{estado}'")
        mensaje_original = mensaje.strip()

        # --- Menú interactivo (solo WhatsApp) ---
        if canal == "wa":
            # Palabra clave: el usuario pide volver al menú principal
            if mensaje_original.lower() in ("menu", "menú", "inicio", "menu principal"):
                redisdb.del_variable(numero, "estado_validacion")
                redisdb.del_variable(numero, "intencion_pendiente")
                redisdb.del_variable(numero, "pregunta_original")
                redisdb.set_variable(numero, "menu_mostrado", "1")
                enviar_menu_wa(message_id, numero, "raiz")
                return
            # Selección desde una WhatsApp List/Button (Zenvia entrega el id como payload)
            if payload:
                tipo_pl, valor_pl = menu.resolver_payload(payload)
                if tipo_pl == "MENU":
                    enviar_menu_wa(message_id, numero, valor_pl)
                    return
                if tipo_pl == "INFO":
                    texto = menu.get_info(valor_pl) or "Información no disponible."
                    enviar_respuesta(canal, message_id, numero, texto)
                    guardar_interaccion(numero, 0, canal, payload, None, texto)
                    return
                if tipo_pl == "ACTION":
                    if valor_pl == "libre":
                        enviar_respuesta(canal, message_id, numero,
                            "Listo, escríbeme tu pregunta directamente y te respondo.")
                        return
                if tipo_pl == "INTENT":
                    # Respuesta directa basada en intent + RAG, sin LLM.
                    intent_pre, pregunta_pre = menu.split_intent_query(valor_pl)
                    # Si el query trae rutas explícitas (tipo/subtipo/valor), las usamos directo
                    # como entities, bypaseando extract_entities (que es ambiguo con valores con _).
                    rutas = [t for t in pregunta_pre.split() if t.count("/") == 2]
                    if rutas:
                        entities = []
                        for r in rutas:
                            t, s, v = r.split("/", 2)
                            entities.append({"tipo": t, "subtipo": s, "valor": v})
                        contexto = conocimiento_general(entities)
                        result = {"intent": intent_pre, "type": "general", "entity": entities, "context": contexto}
                    else:
                        result = process_query(pregunta_pre)
                        if intent_pre:
                            result["intent"] = intent_pre
                        contexto = result.get("context")
                    respuesta = menu.formatear_contexto_general(contexto)
                    if not respuesta:
                        respuesta = "No encontré información para esa opción. Escribe *menu* para volver al menú principal."
                    enviar_respuesta(canal, message_id, numero, respuesta)
                    guardar_interaccion(numero, 0, canal, pregunta_pre, result, respuesta)
                    return
                if tipo_pl == "OTP":
                    intent_pre, pregunta_pre = menu.split_intent_query(valor_pl)
                    cod_persona_b = redisdb.get_variable(numero, "cod_persona")
                    if estado == b"validado" and cod_persona_b:
                        # Ya validado: responder directo desde datos del cliente, sin LLM.
                        cod_persona = cod_persona_b.decode()
                        result = process_query(pregunta_pre)
                        if intent_pre:
                            result["intent"] = intent_pre
                        contexto = contexto_cliente(cod_persona, result)
                        respuesta = menu.formatear_contexto_personal(contexto)
                        enviar_respuesta(canal, message_id, numero, respuesta)
                        guardar_interaccion(numero, cod_persona, canal, pregunta_pre, result, respuesta)
                    else:
                        redisdb.set_variable(numero, "estado_validacion", "esperando_cedula")
                        redisdb.set_variable(numero, "intencion_pendiente", intent_pre)
                        redisdb.set_variable(numero, "pregunta_original", pregunta_pre)
                        redisdb.set_variable(numero, "message_id", message_id)
                        redisdb.set_variable(numero, "modo", "menu")
                        enviar_respuesta(canal, message_id, numero,
                            "Para darte esa información, necesito validar tu identidad. Por favor dame tu número de cédula.")
                    return

        if len(mensaje_original) > 0 :
            # --- 1. Si está esperando cédula ---
            if estado == b"esperando_cedula":
                intencion_val = clasificar_intencion_validacion(mensaje_original)
                if intencion_val == "cancelar":
                    limpiar_estado_validacion(numero)
                    enviar_respuesta(canal, message_id, numero,
                        "Listo, cancelé la solicitud. Escribe *menu* para ver opciones o pregúntame otra cosa cuando quieras.")
                    return
                if intencion_val == "agente":
                    enviar_respuesta(canal, message_id, numero, mensaje_contacto_humano())
                    return
                valida, mensaje, cedula = validar_cedula(mensaje_original)
                if valida:
                    row = buscar_cliente_por_cedula(cedula)
                    if row:
                        cod_persona = row["cod_persona"]
                        nombres = row["nombres"]
                        sexo = row["sexo"]
                        celular = row["celular"]
                        if sexo == "M":
                            saludo = "Bienvenido"
                        if sexo == "F":
                            saludo = "Bienvenida"
                        redisdb.set_variable(numero, "cod_persona", cod_persona)
                        redisdb.set_variable(numero, "estado_validacion", "esperando_otp")
                        redisdb.set_variable(numero, "nombres", row["nombres"])
                        # Generar OTP
                        otp = str(randint(100000, 999999))
                        redisdb.set_variable(numero, "otp", otp, expira=300)
                        logg(f"OTP generado para {cod_persona}: {otp}")
                        sms = f"Este es el código de verificación para consultar tus productos en Real[IA]: {otp}"
                        pid = envia_sms(celular , sms)       
                        cel4d = celular[-4:]
                        if pid > 0:
                            respuesta = f"!{saludo} {nombres}! Te he enviado un código de verificación a su celular terminado en XXX-XXX-{cel4d}. Por favor indicame el código que recibiste."            
                        else:
                            respuesta = f"No fue posible enviar un código de verificación OTP a su celular terminado en {cel4d}. Por favor pase por una sucursal a corregir sus datos."
                        #respuesta = mensaje
                        #enviar_respuesta(canal, message_id, numero, respuesta)
                    else:
                        respuesta = "No encontramos un cliente con esa cédula. Por favor, verifícala."
                        #enviar_respuesta(canal, message_id, numero, respuesta)
                else:
                    respuesta = ("Estoy esperando tu número de cédula (sin guiones).\n"
                                 "• Si quieres terminar, responde *cancelar*.\n"
                                 "• Si prefieres hablar con una persona, responde *agente*.")

            # --- 2. Si está esperando OTP ---
            elif estado == b"esperando_otp":
                intencion_val = clasificar_intencion_validacion(mensaje_original)
                if intencion_val == "cancelar":
                    limpiar_estado_validacion(numero)
                    enviar_respuesta(canal, message_id, numero,
                        "Listo, cancelé la verificación. Escribe *menu* para ver opciones o pregúntame otra cosa cuando quieras.")
                    return
                if intencion_val == "agente":
                    enviar_respuesta(canal, message_id, numero, mensaje_contacto_humano())
                    return
                if intencion_val == "reenviar":
                    enviar_respuesta(canal, message_id, numero, reenviar_otp(numero))
                    return
                if not re.fullmatch(r"\d{6}", mensaje_original):
                    enviar_respuesta(canal, message_id, numero,
                        "Estoy esperando el código de 6 dígitos que te envié por SMS.\n"
                        "• Si no lo recibiste, responde *reenviar*.\n"
                        "• Si prefieres hablar con una persona, responde *agente*.\n"
                        "• Para terminar, responde *cancelar*.")
                    return
                otp_esperado = redisdb.get_variable(numero, "otp")
                if otp_esperado and mensaje_original == otp_esperado.decode():
                    message_id = redisdb.get_variable(numero, "message_id").decode()
                    redisdb.set_variable(numero, "estado_validacion", "validado")
                    redisdb.del_variable(numero, "otp")
                    respuesta = "Validación exitosa. Procesando tu solicitud..."
                    enviar_respuesta(canal, message_id, numero, respuesta)
                    # Ejecutar la intención original
                    intencion = redisdb.get_variable(numero, "intencion_pendiente")
                    pregunta_b = redisdb.get_variable(numero, "pregunta_original")
                    pregunta = pregunta_b.decode()
                    cod_persona = redisdb.get_variable(numero, "cod_persona").decode()
                    # Modo de origen: "menu" -> respuesta directa sin LLM, "libre" -> LLM conversacional
                    modo_b = redisdb.get_variable(numero, "modo")
                    modo = modo_b.decode() if modo_b else "libre"
                    redisdb.del_variable(numero, "modo")

                    logg(f"procesar: pregunta {pregunta} modo={modo}")

                    result = process_query(pregunta)
                    contexto = contexto_cliente(cod_persona, result)

                    try:
                        int_str = intencion.decode()
                        preg_str = pregunta.decode()
                    except:
                        int_str = intencion
                        preg_str = pregunta

                    if modo == "menu":
                        respuesta = menu.formatear_contexto_personal(contexto)
                    else:
                        enviar_respuesta(canal, message_id, numero, "Espera mientras analizo la información solicitada...")
                        respuesta = llamada_llm(numero, int_str, preg_str, contexto)
                else:
                    respuesta = "OTP incorrecto. Intenta nuevamente."

            # --- 3. Si ya está validado ---
            elif estado == b"validado":
                tmp_message_id = message_id
                cod_persona = redisdb.get_variable(numero, "cod_persona").decode()
                message_id = redisdb.get_variable(numero, "message_id").decode()
                redisdb.set_variable(numero, "message_id", tmp_message_id)
                #general, confidencial, intent, contexto = detectar_intencion(mensaje)
                result = process_query(mensaje)
                confidencial = (result["type"] == "personal")
                contexto = result["context"]
                intent = result["intent"]
                if confidencial and cod_persona:
                    #enviar_respuesta(canal, message_id, numero, "Espera mientras analizo la información solicitada...")
                    contexto = contexto_cliente(cod_persona, result)
                    mensaje = normalize_text(mensaje)
                    respuesta = llamada_llm(numero, intent, mensaje, contexto)
                else:
                    #enviar_respuesta(canal, message_id, numero, "Espera mientras analizo la información solicitada...")
                    respuesta = llamada_llm(numero, intent, mensaje, contexto)
                

            # --- 4. Primer mensaje: detectar intención confidencial ---
            else:
                # Primer mensaje de la sesión (estado vacío): mostrar siempre el menú raíz,
                # sin importar el contenido. La bandera 'menu_mostrado' evita repetirlo
                # en mensajes siguientes hasta que expire el hash de sesión (~10 min).
                if canal == "wa" and not payload and not redisdb.get_variable(numero, "menu_mostrado"):
                    redisdb.set_variable(numero, "menu_mostrado", "1")
                    enviar_menu_wa(message_id, numero, "raiz")
                    return
                is_payload = False
                if payload:
                    payload = payload.replace("/", " ")
                    result = process_query(payload)
                    mensaje = f"Informacion sobre {payload}"
                    is_payload = True
                else:
                    result = process_query(mensaje)
                logg(f"procesar: {result}")
                intent = result["intent"]
                contexto = result["context"]
                tipo = result["type"]
                descripcion = None
                try:
                    descripcion = contexto[0]["descripcion"]
                    if contexto[0]["fecha_inicio"]:
                        descripcion += " desde el " + contexto[0]["fecha_inicio"]
                    if contexto[0]["fecha_fin"]:
                        descripcion += " hasta el " + contexto[0]["fecha_fin"]
                    if contexto[0]["horario"]:
                        descripcion += " en horario " + contexto[0]["horario"]
                    if contexto[0]["sitio_web"]:
                        descripcion += "visita nuestra web " + contexto[0]["sitio_web"]
                except:                
                    pass
                #if tipo == 'general':
                #    try:
                #        tipo_ = contexto[0]["tipo"]
                #        subtipo = contexto[0]["subtipo"]
                #        print(f"procesar: tipo_ = {tipo_} :: subtipo = {subtipo}")
                #        if subtipo in ["historia", "filosofia", "politica", "asociado", "estructura", "evento"]:
                #            tipo = 'ayuda'
                #        if tipo_ == "ayuda":
                #            tipo = tipo_
                #    except:
                #        pass
                if tipo == 'personal':
                    redisdb.set_variable(numero, "estado_validacion", "esperando_cedula")
                    redisdb.set_variable(numero, "intencion_pendiente", intent)
                    redisdb.set_variable(numero, "pregunta_original", mensaje)
                    redisdb.set_variable(numero, "message_id", message_id)
                    respuesta = "Para darte esa información, necesito validar tu identidad. Por favor dame tu número de cédula."
                # Descomentar para responder sin usar IA
                elif tipo == 'ayuda':
                    respuesta = contexto[0]["contenido"]
                    if descripcion:
                        respuesta = descripcion + " " + respuesta             
                else:
                    #enviar_respuesta(canal, message_id, numero, "Espera mientras analizo la información solicitada...")
                    respuesta = llamada_llm(numero, intent, mensaje, contexto, is_payload)
        else:
            respuesta = "Estamos presentando inconvenientes, por favor intenta en unos minutos"
        logg(f"procesar: tipo = {tipo} :: respuesta {respuesta}")
        enviar_respuesta(canal, message_id, numero, respuesta)
        guardar_interaccion(numero, cod_persona, canal, mensaje, result, respuesta)

def notify(session_id, body):
    active = redisdb.get_variable(session_id, "active")
    if active == b"1":
        logg("🟢 Pantalla activa: no se envía push")
        return
    
    message = {
        "title": "Real[IA]",
        "body": body
    }    
    sub_json = redisdb.get_subscription(session_id)
    if not sub_json:
        logg(f"No hay suscripción push activa para {session_id}")
        return 
    sub = json.loads(sub_json)
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps(message),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        logg(f"Notificación push enviada a {session_id}")
    except WebPushException as ex:
        loge(f"Error al enviar notificación push: {repr(ex)}")
    except Exception as e:
        loge(f"Error general en envío de notificación push: {e}")   

def enviar_respuesta(canal, message_id, numero, respuesta):
    logg(f"enviar_respuesta:- canal: '{canal}', message_id: '{message_id}', numero: '{numero}',\n- respuesta: '{respuesta}'")
    if canal == "wa":
            enviar_respuesta_wa(message_id, numero, respuesta)
    elif canal == "wc":
        enviar_respuesta_web(message_id, numero, respuesta)

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
            "from": ZENVIA_WANUMBER,
            "to": telefono,
            "contents": [
                {
                    "type": "text",
                    "text": parte
                }
            ]
        }
        response = requests.post(ZENVIA_API, json=payload, headers=ZENVIA_HEADERS, verify=False)
        if response.status_code!= 200:
            logg(f"enviar_respuesta_wa: Respuesta de Zenvia: {response.status_code}")
            #if response.status_code!=403:
            logg(f"enviar_respuesta_wa:\r\n=======INICIO RESPUESTA============\r\n{response.text}\r\n=========FIN RESPUESTA==========")
            #else:
            #    logg(f"enviar_respuesta_wa:\r\n=======INICIO RESPUESTA============\r\n¿Error con Webfiltering?\r\n=========FIN RESPUESTA==========")

def enviar_menu_wa(idRef, telefono, menu_id):
    """Envía un mensaje interactivo tipo list de Zenvia con el menú indicado."""
    contenido = menu.armar_contenido_list(menu_id)
    if not contenido:
        logg(f"enviar_menu_wa: menú '{menu_id}' no encontrado")
        return
    payload = {
        "externalId": "realia",
        "from": ZENVIA_WANUMBER,
        "to": telefono,
        "contents": [contenido],
    }
    response = requests.post(ZENVIA_API, json=payload, headers=ZENVIA_HEADERS, verify=False)
    if response.status_code != 200:
        logg(f"enviar_menu_wa: Respuesta de Zenvia: {response.status_code}")
        logg(f"enviar_menu_wa:\r\n=======INICIO RESPUESTA============\r\n{response.text}\r\n=========FIN RESPUESTA==========")

def enviar_respuesta_web(message_id, session_id, respuesta):
    redisdb.add_web_message(session_id, message_id, respuesta)
    notify(session_id, respuesta)

def llamada_llm(session_id, intencion, pregunta, contexto_str, is_payload = False):   
    try:
        logg(f"llamada_llm: Inicio '{intencion}' '{pregunta}'\r\n{contexto_str}")
        inicio = time.time()        
        chat = ConversationManager(session_id)
        conversacion = json.dumps(chat.get_conversation_history(), ensure_ascii=True)
        #contexto_str = json.dumps(contexto, ensure_ascii=True)
        conocimiento_extra = ""
        if not str(contexto_str).strip():
            conocimiento_extra = load_jsonl_from_file("context_cvr.jsonl")
        #if intencion == 'producto':
        #    respuesta = ""
            #for l in contexto:
            #    respuesta += f"\n- {l['nombre']}: {l['contenido']}"
            # respuesta
        
        respuesta = preguntar_llm(intencion, pregunta, contexto_str, conversacion, conocimiento_extra, max_reintentos=2, modelo=OLLAMA_MODEL, endpoint=OLLAMA_URL, is_payload = is_payload)
        respuesta = respuesta.strip()
        #logg(f"llamada_llm: Inicio 8")
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
        logx(e)
        return "Estamos presentando inconvenientes, por favor intenta en unos minutos"


def fecha_de_texto(texto: str) -> str:
    texto = texto.lower()
    hoy = datetime.now().date()

    if "hoy" in texto:
        return hoy.isoformat()
    elif "mañana" in texto:
        return (hoy + timedelta(days=1)).isoformat()

    # Día de la semana
    for dia_nombre, dia_index in DIAS_SEMANA.items():
        if dia_nombre in texto:
            dias_a_sumar = (dia_index - hoy.weekday()) % 7 or 7
            return (hoy + timedelta(days=dias_a_sumar)).isoformat()

    # Fecha con día y mes: "15 de mayo"
    match = re.search(r"(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)", texto)
    if match:
        dia = int(match.group(1))
        mes = MESES[match.group(2)]
    else:
        # Fecha sin mes: "el 15"
        match = re.search(r"\b(\d{1,2})\b", texto)
        if match:
            dia = int(match.group(1))
            mes = hoy.month
        else:
            return None

    anio = hoy.year
    try:
        fecha_objetivo = datetime(anio, mes, dia).date()
        if fecha_objetivo < hoy:
            fecha_objetivo = datetime(anio + 1, mes, dia).date()
        return fecha_objetivo.isoformat()
    except ValueError:
        return None

def conocimiento_general(entities=None):
    retorno = []
    #logg(f"conocimiento_general: '{entities}'")
    conocimiento = load_jsonl_from_file('context_cvr.jsonl')
    #logg(f"conocimiento_general: JSONL cargado")
    for item in conocimiento:
        for entity in entities:
            if entity["tipo"] == item["tipo"]:
                if entity["subtipo"] == item["subtipo"]:
                    if entity["valor"]:
                        if item["valor"]:
                            if entity["valor"].lower().strip() == item["valor"].lower().strip():
                                retorno.append(item)
                        else: # No hay valor en context
                            retorno.append(item)
                    else: # No hay valor en entities
                        retorno.append(item)
    #logg(f"conocimiento_general: {entities} -> {retorno}")
    return retorno

def construir_prompt(intencion, pregunta, contexto, conversacion, conocimiento_extra=" ", is_payload = False):
    plantilla = ""
    if isinstance(contexto, bytes):
        contexto = contexto.decode('utf-8')
    params = []
    ahora = "\n\n[FECHA_ACTUAL]:\n" + datetime.now().isoformat()
    intencion = intencion.lower()
    JSON = load_json_from_file('plantillas.json')
    if JSON is None:
        logg("construir_prompt: Archivo 'plantillas.json' no está disponible...")
    else:
        if intencion:
            header = JSON["header"]
            task = JSON["task"]
            instruction = JSON["instruction"]
            knowledge = JSON["knowledge"]
            question = JSON["question"]
            rules = JSON["rules"]
            configuracion = json.dumps(JSON["configuracion"])
            try:
                params = JSON[intencion]
            except KeyError as e:
                logg(f"construir_prompt: '{intencion}' no encontrada, usando 'default'.\n{e}")
                intencion = "default"
                params = JSON[intencion]
        else:
            params = JSON["default"]
    
    #if intencion == "default" :
    #    conocimiento_extra = load_jsonl_from_file("context_cvr.jsonl")

    if params:
        logg(f"construir_prompt: Plantilla cargada: '{intencion}'" )
    if len(params) >= 1:
        entidad = params[0]
    if len(params) >= 2:
        inst = params[1]
        if inst:
            instruction += "\n" + inst
    if len(params) >= 3:
        rule = params[2]
        if rule:
            rules += "\n" + rule
    if is_payload:
        plantilla = header + task + instruction + knowledge + rules + ahora
        return "[CONFIGURACIÓN DEL SISTEMA]\n" + configuracion + plantilla.format(
            entidad=entidad,
            contexto=contexto,
            conversacion=conversacion,
            conocimiento_extra=conocimiento_extra,
            pregunta=""
        )
    else:
        plantilla = header + task + instruction + knowledge + rules + ahora + question 
        return "[CONFIGURACIÓN DEL SISTEMA]\n" + configuracion + plantilla.format(
            entidad=entidad,
            contexto=contexto,
            conversacion=conversacion,
            conocimiento_extra=conocimiento_extra,
            pregunta=pregunta
        )
    
def validar_respuesta_json(respuesta_texto):
    """
    Valida que la respuesta de Mistral esté en formato JSON correcto.
    """
    try:
        data = json.loads(respuesta_texto)
        if isinstance(data, dict) and "intencion" in data and "entidad" in data:
            return data
        else:
            return None
    except json.JSONDecodeError:
        return None

def detectar_intencion(pregunta):    
    result = process_query(pregunta)
    logg(f"detectar_intencion('{pregunta}') => {result}")
    intent = result["intent"]
    contexto = result["context"]
    entidad = result["entity"]
    tipo = result["type"]
    if intent:
        if contexto:
            if tipo == 'personal':
            #if intent == 'cedula':
                return False, True, intent, entidad
            #if intent == 'saldo':
            #    return False, True, intent, contexto
            return True, False, intent, contexto
        
    return False, False, None, None

def search_sucursales(filters: Dict) -> List[Dict]:
        """Busca sucursales según filtros"""
        results = []
        for suc in data['sucursales']:
            match = True
            for key, values in filters.items():
                if key == 'ubicacion':
                    if not (suc['municipo'] in values or suc['provincia'] in values or suc['direccion'] in values):
                        match = False
                elif key in suc and suc[key] not in values:
                    match = False
            if match:
                results.append(suc)
        return results

def get_product_info(product_name: str) -> Optional[Dict]:
        """Obtiene información de un producto específico"""
        # Buscar en productos principales
        for product_type, details in data['productos'].items():
            if product_type == product_name:
                return {'tipo': product_type, 'info': details}
            
            # Buscar en subcategorías
            if isinstance(details, dict):
                for sub_type, sub_details in details.items():
                    if sub_type == product_name:
                        return {'tipo': product_type, 'subtipo': sub_type, 'info': sub_details}
        
        return None
def get_service_info(service_name: str) -> Optional[Dict]:
        """Obtiene información de un servicio específico"""
        # Buscar en servicios principales
        for service_type, details in data['servicios'].items():
            if service_type == service_name:
                return {'tipo': service_type, 'info': details}
            
            # Buscar en subservicios (como odontología)
            if isinstance(details, dict):
                for sub_type, sub_details in details.items():
                    if sub_type == service_name:
                        return {'tipo': service_type, 'subtipo': sub_type, 'info': sub_details}
                    # Buscar en servicios dentales
                    if isinstance(sub_details, dict) and 'servicios' in sub_details:
                        for dental_service, price in sub_details['servicios'].items():
                            if dental_service == service_name:
                                return {
                                    'tipo': service_type,
                                    'subtipo': sub_type,
                                    'servicio': dental_service,
                                    'precio': price
                                }
        
        return None

def clasificar_intencion_validacion(texto):
    """Clasifica intenciones del usuario durante esperando_cedula/esperando_otp.
    Devuelve 'cancelar', 'agente', 'reenviar' o None."""
    t = normalize_text(texto)
    kw_cancelar = ("cancela", "cancelar", "olvidalo", "ya no me interesa",
                   "dejalo", "no me interesa")
    if any(k in t for k in kw_cancelar):
        return "cancelar"
    kw_agente = ("agente", "humano", "persona", "asesor", "operador",
                 "conectame", "hablar con alguien", "hablar con una persona",
                 "quiero hablar con", "ponme con")
    if any(k in t for k in kw_agente):
        return "agente"
    kw_reenviar = ("reenviar", "reenvio", "otro codigo", "no recibo",
                   "no llego", "no me llego", "no me ha llegado",
                   "mandalo de nuevo", "envialo de nuevo", "manda otro",
                   "envia otro")
    if any(k in t for k in kw_reenviar):
        return "reenviar"
    return None

def limpiar_estado_validacion(numero):
    """Limpia las variables del flujo de validación de identidad."""
    for campo in ("estado_validacion", "intencion_pendiente", "pregunta_original",
                  "message_id", "modo", "otp"):
        redisdb.del_variable(numero, campo)
    rdb = redisdb.getRedis()
    rdb.delete(f"otp_ratelimit:{numero}")

def _telefono_cooperativa():
    """Lee el teléfono central de la cooperativa desde context_cvr.jsonl
    (entrada tipo=empresa, subtipo=contacto, valor=telefono)."""
    try:
        ctx = load_jsonl_from_file('context_cvr.jsonl') or []
        for item in ctx:
            if (item.get("tipo") == "empresa" and item.get("subtipo") == "contacto"
                    and item.get("valor") == "telefono"):
                num = (item.get("contenido") or "").strip()
                digits = "".join(c for c in num if c.isdigit())
                if len(digits) == 11 and digits.startswith("1"):
                    return f"+1 {digits[1:4]}-{digits[4:7]}-{digits[7:]}"
                if len(digits) == 10:
                    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:]}"
                return num or None
    except Exception as e:
        loge(f"_telefono_cooperativa: error leyendo context_cvr.jsonl: {e}")
    return None

def mensaje_contacto_humano():
    """Mensaje para cuando el cliente pide hablar con un agente."""
    tel = _telefono_cooperativa()
    if tel:
        return (f"Para hablar con una persona, por favor llama a la cooperativa al {tel}. "
                "Si prefieres seguir por aquí, escribe *menu* para ver las opciones.")
    return ("Para hablar con una persona, por favor llama a la cooperativa. "
            "Si prefieres seguir por aquí, escribe *menu* para ver las opciones.")

def reenviar_otp(numero):
    """Regenera y reenvía el OTP por SMS, con rate-limit de 60s."""
    rdb = redisdb.getRedis()
    rl_key = f"otp_ratelimit:{numero}"
    if rdb.get(rl_key):
        return "Acabo de enviarte un código. Espera un momento antes de pedir otro."
    cod_b = redisdb.get_variable(numero, "cod_persona")
    if not cod_b:
        return ("No pude reenviar el código porque tu sesión expiró. "
                "Escribe *menu* para empezar de nuevo o *agente* para hablar con una persona.")
    cliente = buscar_cliente(cod_b.decode())
    if not cliente or not cliente.get("celular"):
        return ("No pude reenviar el código. Por favor pasa por una sucursal "
                "o responde *agente* para hablar con una persona.")
    otp = str(randint(100000, 999999))
    redisdb.set_variable(numero, "otp", otp, expira=300)
    rdb.setex(rl_key, 60, "1")
    envia_sms(cliente["celular"],
              f"Este es el código de verificación para consultar tus productos en Real[IA]: {otp}")
    logg(f"OTP reenviado para {cod_b.decode()}: {otp}")
    cel4d = cliente["celular"][-4:]
    return f"Te reenvié el código al celular terminado en XXX-XXX-{cel4d}. Por favor indícame el código que recibiste."

def es_saludo(texto):
    saludos = [
        "hola", "buenos días", "buen dia", "buena tarde","buenas tardes", "buenas noches", "buena noche", "qué tal", "cómo estás", "cómo está",
        "cómo te va", "cómo le va", "saludos", "buenas", "muy buenos días", "muy buenas tardes",
        "muy buenas noches", "hey", "hola hola", "holi", "holis", "qué onda", "qué hay", "qué hubo",
        "cómo andas", "cómo va todo", "qué pasa", "qué cuentas", "qué hay de nuevo", "qué más",
        "buenas noches tenga", "buenos días tenga", "buenos días por aquí", "buenas tardes por aquí",
        "saludos cordiales", "un saludo", "buenos días estimado", "buenas tardes estimado",
        "hola buenas", "hola buen día", "qué tal buenos días", "qué tal buenas tardes", "qué tal buenas noches"
    ]

    texto = normalize_text(texto)
    for saludo in saludos:
        saludo_norm = normalize_text(saludo)
        if saludo_norm in texto:
            logg(f"saludo '{saludo_norm}' -> '{texto}'")
            return True
    return False

def es_cierre(texto):
    frases_cierre = [
        "gracias", "muchas gracias", "no, gracias", "está bien", "perfecto", "entendido", "ok", "de acuerdo", "listo",
        "eso es todo", "finalizado", "finalizar", "cerramos", "nada más", "no necesito más", "todo claro", "bye", "adiós",
        "hasta luego", "nos vemos", "hasta la próxima", "chau", "ya terminé", "ya resolví", "solucionado", "excelente",
        "claro", "sin más", "por ahora está bien", "concluyo", "cierro", "acabamos", "muchas gracias por su ayuda",
        "muchas gracias, fue todo", "por mi parte todo claro", "asunto cerrado", "quedó claro", "hasta aquí",
        "todo correcto", "así está bien", "seguimos luego", "luego hablamos", "gracias por todo", "no más consultas",
        "no tengo más preguntas"
    ]

    texto = normalize_text(texto)
    for frase in frases_cierre:
        frase_norm = normalize_text(frase)
        if frase_norm in texto:
            return True
    return False

def process_query(query: str) -> dict:
        """Procesa una consulta del usuario y devuelve una respuesta"""
        result = {
                "intent": None,
                "type": "general",
                "entity": None,
                "context": None
            }
        tipo = None
        logg(f"process_query: query = '{query}'")
        if es_saludo(query):
            logg(f"process_query: es saludo")
            tipo = "ayuda"
            intent = 'saludo'
        elif es_cierre(query):
            logg(f"process_query: es cierre")
            tipo = "ayuda"
            intent = 'cierre'
        else:
            tipo = "general"
            intent = detect_intent(query)
        
        posesivos = ["mi ", "mis ", "de mi", "de mis"]
        if any(p in query for p in posesivos):
            tipo = "personal"            
        
        local_entities = extract_entities(intent, query)
        if intent == "saldo":
            tipo = "personal"
        result["intent"] = intent
        result["type"] = tipo
        result["entity"] = local_entities
        logg(f"process_query: intent type '{tipo}' intent = '{intent}' entities = '{local_entities}'")
        if result["type"] == "general":
            logg(f"process_query: buscando entidades generales '{intent}'")
            contexto = conocimiento_general(local_entities)
            if len(local_entities) > 0:
                filtros = local_entities[0].get("filtros")
                if filtros:
                    logg(f"process_query: Procesando filtros {filtros}")
                    ctx = []
                    for filtro in filtros:
                       # logg(f"process_query: evaluando filtro {filtro} '{query}'")
                        f = ""
                        for c in contexto:
                            if f != c.get(filtro):
                                f = c.get(filtro)
                                if f:
                                    f2 = normalize_text(f).split(" ")
                                    #logg(f"process_query: evaluando {filtro} -> {f2} '{query}'")
                                    if any(palabra in query for palabra in f2): # Busco por texto
                                        logg(f"process_query: agregando {filtro} -> {f2} '{query}'")
                                        ctx.append(c)
                                    else: # Busco por fecha
                                        fecha = fecha_de_texto(query)
                                        if fecha:
                                            if c.get(filtro) == fecha:                                
                                                ctx.append(c)
                    #logg(f"process_query: Econtre {ctx}")
                    if len(ctx) > 0: 
                        contexto = ctx
            result["context"] = contexto
            return result
        elif result["type"] == "personal": #Personales que requieren validacion OTP
            logg(f"process_query: entidades personales '{intent}'")
            result["context"] = ""
            return result       
        else: # Es saludo o cierre
            logg(f"process_query: entidades de '{intent}'")
            entities = []
            entity = {"tipo": "ayuda", "subtipo": intent, "valor": intent}
            entities.append(entity)
            contexto = conocimiento_general(entities)
            result["entity"] = entity
            result["context"] = contexto
            return result       
        #

def normalize_text(text: str) -> str:
    """Normaliza texto para comparación"""
    text = text.lower().strip()
    replacements = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ü': 'u', 'ñ': 'n'
        }
    stopwords = {'de', 'la', 'lo', 'el', 'en', 'a', 'como', 'y', 'o', 'una', 'un', 'las', 'los', 'al', 'del', 'para', 'por', 'con', 'que', 'se', 'su', 'tu'}

    # Convierte a minúsculas y elimina signos de puntuación
    text = re.sub(r'[^\w\s]', '', text)
    # Separa la oración en palabras
    palabras = text.split()
    # Filtra las palabras que no están en la lista de stopwords
    palabras_filtradas = [p for p in palabras if p not in stopwords]
    # Une nuevamente las palabras
    text = ' '.join(palabras_filtradas)
    
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    # Reemplazar sinónimos
    synonyms = load_json_from_file('synonyms.json')
    for syn, main in synonyms.items():
        text = text.replace(syn, main)
    return text.strip()

# Cache de archivos de configuración (intents, entities, context, synonyms, plantillas, ...).
# Re-lee desde disco solo cuando cambia el mtime del archivo.
_file_cache = {}  # full_path -> (mtime, data)


def _cached_read(filepath, parser):
    full_path = f"{BASE_PATH}/{filepath}"
    try:
        mtime = os.path.getmtime(full_path)
    except OSError:
        logg(f"_cached_read: File '{filepath}' not accessible, ignoring...")
        return None
    cached = _file_cache.get(full_path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = parser(full_path)
        _file_cache[full_path] = (mtime, data)
        return data
    except Exception as e:
        logg(f"_cached_read: error parsing '{filepath}': {e}")
        return cached[1] if cached else None


def _parse_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _parse_jsonl(path):
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for linea in f:
            s = linea.strip()
            if s and not s.startswith("#"):
                out.append(json.loads(linea))
    return out


def load_json_from_file(filepath) -> dict:
    return _cached_read(filepath, _parse_json)


def load_jsonl_from_file(filepath) -> dict:
    return _cached_read(filepath, _parse_jsonl)

def detect_intent2(query: str) -> str:
    """Detecta la intención principal del usuario"""
    query = normalize_text(query)
    logg(f"detect_intent('{query}')")
    intents = load_json_from_file("intents.json")

    for intent, keywords in intents.items():
        if any(keyword in query for keyword in keywords):
            return intent
    
    query = query.replace('-','')
    if query.isdigit() and len(query) in [10, 11]:
        return 'cedula'
    
    return 'general'
import re

def detect_intent(query: str) -> str:
    """Detecta la intención principal del usuario basada en cantidad de coincidencias"""
    query = normalize_text(query)
    logg(f"detect_intent('{query}')")
    intents = load_json_from_file("intents.json")

    intent_scores = {}

    for intent, keywords in intents.items():
        count = sum(1 for keyword in keywords if re.search(r'\b' + re.escape(keyword) + r'\b', query))
        if count > 0:
            logg(f"detect_intent '{intent}' {count}")
            intent_scores[intent] = count

    if intent_scores:
        # Devuelve el intent con mayor número de coincidencias
        return max(intent_scores, key=intent_scores.get)

    return 'general'

def extract_entities(intent, query: str) -> Dict:
    query = normalize_text(query)
    logg(f"extract_entities('{intent}', '{query}')")
    found = []
    matchs = {}
    local_entities = load_jsonl_from_file('entities.jsonl')
    max_coincidencias = 0
    match_found = 0
    for item in local_entities:
        if intent == item["tipo"]:
            #logg(f"extract_entities: item: {item} in '{query}'")
            for campo in ['tipo', 'subtipo', 'valor', 'nombre', 'descripcion', 'contenido', 'fecha', 'municipio', 'provincia', 'pais', 'telefonos', 'extensiones']:
                if campo in item:
                    try:
                        palabras_clave = []
                        for v in item.values():
                            #logg(f"extract_entities: v = {v}")
                            palabras_clave.extend(v.lower().replace('_', ' ').split())
                        palabras_frase = query.split()
                        coincidencias = sum(1 for palabra in palabras_clave if palabra in palabras_frase)
                        if coincidencias > 0:                            
                            if coincidencias >= max_coincidencias:
                                max_coincidencias = coincidencias
                                matchs[match_found] = {"coincidencias": coincidencias, "entity": item}
                                match_found += 1
                                logg(f"extract_entities: Coincidencias {palabras_clave} -> {palabras_frase} :: encontradas: {coincidencias}")
                            
                    except AttributeError as e:
                        loge(f"extract_entities: Error {e}")
                        pass # No pude determinar coincidencias
                    campo_arr = normalize_text(str(item[campo])).split("_")
                    for c in campo_arr:
                        #logg(f"extract_entities: '{intent}' campo: {campo} = '{c}'  in '{query}'")
                        if c in query:
                            found.append(item)
                            logg(f"extract_entities: {campo} found: {item} -> '{c}' in '{query}'")
    if matchs:
       # Determinar la coincidencia máxima
        max_coincidencias = max(item['coincidencias'] for item in matchs.values())
        # Filtrar todos los objetos con la coincidencia máxima
        mejores_objetos = [item['entity'] for item in matchs.values() if item['coincidencias'] == max_coincidencias]
        
        objetos_sin_duplicados = []
        objetos_vistos = set()

        for obj in mejores_objetos:
            obj_tuple = tuple(sorted(obj.items()))
            if obj_tuple not in objetos_vistos:
                objetos_vistos.add(obj_tuple)
                objetos_sin_duplicados.append(obj)
        
        logg(f"extract_entities: Las mejores coincidencias {objetos_sin_duplicados}")
        found = objetos_sin_duplicados
    # Fallback: si no se encontró nada, intentar buscar por municipio/provincia/valor
    if not found:
        tokens = set(query.split())
        for item in (local_entities or []):
            try:
                # Normalizar varios campos que podrían contener el nombre de la localidad
                campos = []
                for k in ('municipio', 'provincia', 'valor', 'nombre'):
                    if k in item and item.get(k):
                        campos.extend(normalize_text(str(item.get(k))).split())
                if any(tok in tokens for tok in campos):
                    found.append(item)
                    logg(f"extract_entities (fallback): encontrado por municipio/valor: {item}")
            except Exception as e:
                logg(f"extract_entities fallback error: {e}")
    return found

def llama_ollama(endpoint, modelo, prompt):
    respuesta_llm = ""
    try:
        response = requests.post(endpoint, json={
            "model": modelo,
            "prompt": prompt,
            "stream": False
        })

        if response.status_code != 200:
            logg(f"preguntar_llm: Error en conexión (código {response.status_code})")
        # Intentar leer la respuesta, pero si hay problema devolver cadena vacía
        try:
            respuesta_llm = response.json().get("response", "")
            if isinstance(respuesta_llm, str):
                respuesta_llm = respuesta_llm.replace("[RESPUESTA]:", "")
        except Exception as e:
            logx(e)
            respuesta_llm = ""
    except Exception as e:
        logx(e)
        respuesta_llm = ""
    return respuesta_llm

def llama_openai(endpoint, modelo, prompt):
    url = f"{endpoint}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}"
    }
    payload = {
        "model": modelo,
        "store": True,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        # Aumentar timeout porque la generación puede tardar (carga de modelo, CPU)
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
        response.raise_for_status()
        respuesta = response.json()
        # Extraer contenido de forma segura
        try:
            return respuesta['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            logx(e)
            return ""
    except requests.RequestException as e:
        logx(e)
        return ""
    except Exception as e:
        logx(e)
        return ""

def preguntar_llm(intencion, pregunta, contexto, conversacion, conocimiento_extra, max_reintentos=2, modelo="mistral:7b-instruct", endpoint="http://localhost:11434/api/generate", is_payload = False):
    """
    Envía la pregunta al modelo llm, valida la respuesta como JSON,
    reintenta si es necesario, y maneja error amigablemente.
    """
    #pregunta = normalize_text(pregunta)
    prompt = construir_prompt(intencion, pregunta, contexto, conversacion, conocimiento_extra, is_payload)
    logg(f"preguntar_llm: '{intencion}' -> '{pregunta}'")
    #logg(f"\r\n=======INICIO CONTEXTO============\r\n{contexto}\r\n=========FIN CONTEXTO==========")
    logg(f"preguntar_llm:\r\n=======INICIO PROMPT============\r\n{prompt}\r\n=========FIN PROMPT==========")
    logg("preguntar_llm: Analizando respuesta...")
    for intento in range(max_reintentos + 1):
        try:
            logg(f"preguntar_llm: endpoint {endpoint}")
            respuesta_llm = llama_openai(endpoint, modelo, prompt) # llama_ollama(endpoint, modelo, prompt)
            if respuesta_llm:
                logg(f"preguntar_llm: '{intencion}' \r\nUsuario: {pregunta} \r\nAsistente: {respuesta_llm}")
                return respuesta_llm  # JSON correcto
            else:
                logg(f"preguntar_llm: Intento {intento + 1}: Respuesta inválida, reintentando...")
                time.sleep(0.5)

        except Exception as e:
            logg(f"preguntar_llm: Error durante consulta a LLM: {e}")
            continue

    # Si no se pudo validar en todos los intentos:
    return "Estamos presentando inconvenientes, por favor intenta en unos minutos"

#######
# Login page
login_html = """
<!DOCTYPE html>
<html lang="es">
<head><title>Login</title></head>
<body>
    <h2>Login</h2>
    <form method="POST">
        Usuario: <input type="text" name="usuario" required><br>
        Contraseña: <input type="password" name="password" required><br>
        <button type="submit">Ingresar</button>
    </form>
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <ul>
        {% for message in messages %}
          <li>{{ message }}</li>
        {% endfor %}
        </ul>
      {% endif %}
    {% endwith %}
</body>
</html>
"""

# Página de consulta
consulta_html = """
<!DOCTYPE html>
<html lang="es">
<head><title>Consulta</title></head>
<body>
    <h2>Consulta SQLite</h2>
    <a href="{{ url_for('logout') }}">Cerrar sesión</a>
    <table border="1">
        <tr>{% for col in columnas %}<th>{{ col }}</th>{% endfor %}</tr>
        {% for fila in filas %}
        <tr>{% for item in fila %}<td>{{ item }}</td>{% endfor %}</tr>
        {% endfor %}
    </table>
</body>
</html>
"""
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        if usuario == 'jamalena' and password == 'admin':
            session['usuario'] = usuario
            return redirect(url_for('interacciones'))
        else:
            flash('Credenciales incorrectas')
    return render_template_string(login_html)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/interacciones')
def interacciones():
    #if 'usuario' not in session:
    #    return redirect(url_for('login'))
    columnas, filas = obtener_interacciones()
    return render_template_string(consulta_html, filas=filas, columnas=columnas)

#######    
if __name__ == "__main__":
    logg(f"api_llm: Usando modelo '{OLLAMA_MODEL}' en '{OLLAMA_URL}'")
    logg(f"========================================================")
    app.run(host="0.0.0.0", port=8000, debug=True)
