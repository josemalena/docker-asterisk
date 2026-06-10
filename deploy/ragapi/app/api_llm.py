#!/opt/rag/bin/python
#api_llm.py: Lógica de negocio principal, manejo de rutas y procesamiento de mensajes para la aplicación RAG API.
import requests
import uuid
import time
import json
import re
import os
import logging
import urllib3
import hashlib
#from openai import OpenAI
from typing import Dict, List, Optional
from flask import Flask, request, jsonify, send_from_directory, session, request, redirect, url_for, render_template, render_template_string, flash, abort
from flask_session import Session
from pywebpush import webpush, WebPushException
from threading import Thread
from datetime import datetime, timedelta, timezone
from random import randint

# Base de datos
from rag_db import ConversationManager, obtener_interacciones, obtener_conversaciones, obtener_mensajes_conversacion, obtener_conversacion_header, obtener_respuestas_plantilla, guardar_interaccion, disable_log, enable_log, envia_sms, buscar_cliente_por_cedula, buscar_cliente, contexto_cliente, fin, logg, loge, logx, validar_cedula, buscar_notificaciones_por_destino, buscar_notificaciones_por_destinos, validar_usuario, guardar_mensaje, nombre_usuario, marcar_atendido_por, obtener_atendido_por, cerrar_conversacion, transferir_conversacion, guardar_nota_interna, guardar_cliente

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
# Si USE_LLM=false, el bot responde sólo desde menú/RAG; las llamadas al LLM
# (clasificador fallback y generador conversacional) responden con un mensaje
# que redirige al usuario al menú. Útil mientras se mejora el entrenamiento.
USE_LLM = os.getenv("USE_LLM", "false").strip().lower() in ("true", "1", "yes", "on", "si")
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

# Configuración de encuestas (endpoint externo)
ENCUESTA_URL = os.getenv("ENCUESTA_URL", "http://172.17.0.99/api/external/link")
ENCUESTA_API_KEY = os.getenv("ENCUESTA_API_KEY")
try:
    ENCUESTA_ID = int(os.getenv("ENCUESTA_ID", 0))
except Exception:
    ENCUESTA_ID = 0


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

def _reenviar_plantilla_zenvia(numero, templateId, fields):
    """Reenvía una plantilla Zenvia al número dado usando el mismo templateId y fields originales."""
    try:
        payload = {
            "externalId": "realia",
            "from": ZENVIA_WANUMBER,
            "to": numero,
            "contents": [{
                "type": "template",
                "templateId": templateId,
                "fields": fields
            }]
        }
        response = requests.post(ZENVIA_API, json=payload, headers=ZENVIA_HEADERS, verify=False)
        if response.status_code not in (200, 201):
            loge(f"_reenviar_plantilla_zenvia: error {response.status_code}: {response.text}")
        else:
            logg(f"_reenviar_plantilla_zenvia: plantilla '{templateId}' reenviada a {numero}")
    except Exception as e:
        loge(f"_reenviar_plantilla_zenvia: excepción: {e}")


def _manejar_respuesta_plantilla(numero, mensaje, message_id, detalle=None):
    """Detecta si el mensaje entrante de WA es la respuesta a una notificación de plantilla
    enviada por otro sistema (gobernanza, encuestas, etc.) y responde automáticamente.

    Flujo:
      1. Si hay un flujo activo de validación → no interceptar.
      2. Si ya respondimos antes a la plantilla de este número → no interceptar.
      3. Buscar en Redis el caché de la notificación (last_templateId / last_fields).
         Si no está, consultar Oracle via buscar_notificaciones_por_destino.
      4. Con los fields encontrados:
         - Si existe 'url' → responder con el enlace personalizado.
         - Si no existe 'url' → agradecer y reenviar la plantilla.
      5. Marcar 'template_replied' para no repetir en mensajes siguientes.
      6. Marcar 'menu_mostrado' para que el flujo normal no imponga el menú.

    Retorna True si el mensaje fue interceptado (no debe pasar a procesar).
    """
    try:
        # 1. No interceptar si hay flujo activo de validación/OTP
        estado = redisdb.get_variable(numero, "estado_validacion")
        if estado:
            logg(f"_manejar_respuesta_plantilla: estado_validacion activo ({estado}), omitiendo")
            return False

        rdb = redisdb.getRedis()

        # 2. No interceptar si ya respondimos antes
        ya_respondido = rdb.hget(f"wa_orig:{numero}", "template_replied")
        if ya_respondido and ya_respondido.decode() == "1":
            logg(f"_manejar_respuesta_plantilla: plantilla ya atendida para {numero}")
            return False

        # 3a. Intentar leer del caché en Redis
        templateId = None
        fields = None
        outgoing_msg_id = None

        fields_b = rdb.hget(f"wa_orig:{numero}", "last_fields")
        templateId_b = rdb.hget(f"wa_orig:{numero}", "last_templateId")
        outgoing_id_b = rdb.hget(f"wa_orig:{numero}", "last_notificacion_id")

        try:
            if fields_b:
                fields = json.loads(fields_b.decode())
            if templateId_b:
                templateId = json.loads(templateId_b.decode())
            if outgoing_id_b:
                outgoing_msg_id = outgoing_id_b.decode()
        except Exception as e:
            loge(f"_manejar_respuesta_plantilla: error leyendo Redis caché: {e}")
            fields = None
            templateId = None

        # 3b. Si no hay caché, consultar Oracle
        if not fields:
            logg(f"_manejar_respuesta_plantilla: sin caché, consultando Oracle para {numero}")
            matches = buscar_notificaciones_por_destino(numero, tipo_notificacion=2, limit=1)
            if not matches:
                logg(f"_manejar_respuesta_plantilla: no hay notificaciones para {numero}")
                return False
            m = matches[0]
            detalle = m.get('detalle')
            if not isinstance(detalle, dict):
                return False
            # Extraer id del mensaje saliente (campo raíz del JSON)
            outgoing_msg_id = str(detalle.get('id') or m.get('id') or '')
            contents_out = detalle.get('contents')
            if not isinstance(contents_out, list) or not contents_out:
                return False
            first = contents_out[0]
            templateId = first.get('templateId') or first.get('templateID')
            fields = first.get('fields')
            if not fields:
                logg(f"_manejar_respuesta_plantilla: notificación sin fields para {numero}")
                return False
            # Cachear en Redis (24h)
            try:
                rdb.hset(f"wa_orig:{numero}", "last_templateId", json.dumps(templateId, ensure_ascii=False))
                rdb.hset(f"wa_orig:{numero}", "last_fields", json.dumps(fields, ensure_ascii=False))
                rdb.hset(f"wa_orig:{numero}", "last_notificacion_id", outgoing_msg_id)
                rdb.expire(f"wa_orig:{numero}", 86400)
                redisdb.set_variable(numero, "templateId", json.dumps(templateId, ensure_ascii=False))
                guardar_cliente(numero)
                logg(f"_manejar_respuesta_plantilla: caché actualizado en Redis para {numero} | templateId={templateId}")
                
            except Exception as e:
                loge(f"_manejar_respuesta_plantilla: error cacheando en Redis: {e}")

        if not fields:
            return False

        # 4. Construir respuesta según presencia de URL
        nombre = fields.get('nombre', '')
        # Buscar URL en distintos nombres de campo habituales
        url = (fields.get('url') or fields.get('link') or
               fields.get('enlace') or fields.get('URL') or '')
        # Descripción del motivo/evento (primer campo descriptivo que encontremos)
        descripcion = (fields.get('nombre_evento') or fields.get('consejos') or
                       fields.get('accion') or fields.get('asunto') or '')

        saludo = f"Hola *{nombre}*! 👋\n" if nombre else ""

        if url:
            partes = [saludo.rstrip()]
            if descripcion:
                partes.append(f"Recibimos tu respuesta sobre *{descripcion}*.")
                partes.append(f"Puedes acceder o confirmar tu participación con el siguiente enlace:\n{url}")
            else:
                partes.append(f"Puedes completar la encuesta de satisfacción con el siguiente enlace:\n{url}")
            partes.append("\nSi necesitas más información, escribe *menu* para ver las opciones disponibles.")
            respuesta = "\n".join(p for p in partes if p)
        else:
            partes = [saludo.rstrip()]
            if descripcion:
                partes.append(f"Gracias por tu respuesta sobre *{descripcion}*.")
            else:
                partes.append("Gracias por tu respuesta.")
            partes.append("Te reenviamos la información para que la tengas a mano.")
            respuesta = "\n".join(p for p in partes if p)

        logg(f"_manejar_respuesta_plantilla: respondiendo a {numero} | templateId={templateId} | url={url}")
        enviar_respuesta_wa(message_id, numero, respuesta)

        # Si no hay URL, reenviar la plantilla original
        if not url and templateId and fields:
            _reenviar_plantilla_zenvia(numero, templateId, fields)

        # 5. Marcar como atendido y activar menu_mostrado para flujo posterior normal
        try:
            rdb.hset(f"wa_orig:{numero}", "template_replied", "1")
            redisdb.set_variable(numero, "menu_mostrado", "1")
        except Exception as e:
            loge(f"_manejar_respuesta_plantilla: error marcando estado: {e}")

        # 6. Persistir la interacción en SQLite (incluir fields para no re-consultar Oracle)
        try:
            guardar_interaccion(
                numero, 0, "wa", mensaje,
                {"intent": "respuesta_plantilla", "type": "template",
                 "templateId": templateId, "outgoing_msg_id": outgoing_msg_id,
                 "fields": fields},
                respuesta
            )
        except Exception as e:
            loge(f"_manejar_respuesta_plantilla: error guardando interacción: {e}")

        return True

    except Exception as e:
        loge(f"_manejar_respuesta_plantilla: error inesperado: {e}")
        return False


@app.route('/webhook/zenvia', methods=['POST', 'GET'])
def zenvia_webhook():
    client_info = getClientInfo(request)
    #logg(f"Webook - Request: {client_info}")
    #if request.method != 'POST':
    #    return redirect(url_for('home'))
    data = request.json
    #logg(f"Webook - Mensaje: {data}")
    # 1. Filtrado robusto de mensajes
    if data.get("direction") != "IN" or not data.get("message"):
        return jsonify({"status": "ignored"}), 200
    
    # 2. Ignorar mensajes duplicados o propios
    message_id = data["message"].get("id")
    if message_id and message_id == session.get("last_processed_msg"):
        return jsonify({"status": "duplicate"}), 200
    
    # 3. Extraer datos seguros
    try:
        content = data["message"]["contents"][0]
        # Detectar archivos/attachments en WA: type distinto de 'text' o claves fileUrl/fileName
        c_type = content.get("type", "text")
        mensaje = content.get("text", "")
        mensaje = mensaje.strip() if isinstance(mensaje, str) else ""
        payload = content.get("payload", "")
        numero = data["message"]["from"]
        # Nombre del visitante (firstName del webhook) para identificar al remitente.
        visitor = data["message"].get("visitor") or {}
        nombre_remitente = visitor.get("firstName") or visitor.get("name") or numero
        guardar_mensaje(
            session_id=message_id,
            telefono=numero,
            canal="wa",
            direccion="IN",
            contenido=mensaje or payload,
            enviado_por=nombre_remitente,
            metadata=json.dumps(data)
        )
    except (KeyError, IndexError):
        return jsonify({"status": "invalid_format"}), 400

    # Si el contenido proviene de WhatsApp y no es texto (archivo, audio, imagen),
    # responder que no aceptamos archivos y enviar el menú raíz.
    try:
        is_file = False
        if c_type and str(c_type).lower() != "text":
            is_file = True
        if not is_file and isinstance(content, dict):
            for k in ("fileUrl", "fileName", "fileMimeType", "fileSizeBytes", "file_url"):
                if k in content:
                    is_file = True
                    break
        if is_file:
            aviso = ("Lo siento, por el momento no puedo recibir archivos. "
                     "Por favor envía sólo mensajes de texto.")
            try:
                enviar_respuesta("wa", message_id, numero, aviso)
                enviar_menu("wa", message_id, numero, "raiz")
            except Exception as e:
                loge(f"Error enviando aviso/menu por archivo entrante: {e}")
            return jsonify({"status": "file_ignored"}), 200
    except Exception as e:
        loge(f"Error detectando tipo de contenido en webhook Zenvia: {e}")

    # 4. Procesamiento condicional
    if not mensaje.strip():
        return jsonify({"status": "empty_message"}), 200

    # 5. Guardar ID para evitar reprocesamiento
    session["last_processed_msg"] = message_id
    
    logg(f"zenvia_webhook: Procesando: {numero}: {mensaje}")

    # 6. Si el mensaje es respuesta a una plantilla enviada por otro sistema, interceptar
    if _manejar_respuesta_plantilla(numero, mensaje, message_id, data):
        return jsonify({"status": "template_reply_handled"}), 200

    # 7. Lógica de negocio normal
    Thread(target=procesar, args=(numero, mensaje, payload, "wa", message_id)).start()

    # 8. Respuesta inmediata para evitar timeout
    return jsonify({"status": "processing"}), 200

@app.route("/webchat/mensajes")
def mensajes_webchat():
    session_id = session.get("session_id")
    mensajes = redisdb.get_web_messages(session_id)
    return jsonify({"mensajes": mensajes})

@app.route("/chat", methods=["POST"])
def web_chat():
    data = request.get_json() or {}

    mensaje = (data.get("message") or "").strip()
    payload = (data.get("payload") or "").strip() or None
    logg(f"web_chat: Recibi: mensaje='{mensaje}' payload='{payload}'")

    if not mensaje and not payload:
        return jsonify({"error": "Falta 'message' o 'payload'"}), 400
    session_id = session.get("session_id")
    guardar_mensaje(
        session_id=session_id,
        canal="wc",
        direccion="IN",
        contenido=mensaje or payload,
        metadata=json.dumps(data)
    )
    logg(f"web_chat: session_id: '{session_id}'")
    message_id = str(uuid.uuid4())

    Thread(target=procesar, args=(session_id, mensaje or payload, payload, "wc", message_id)).start()

    return jsonify({"status": "processing", "message_id": message_id}), 200

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

        # --- Atención humana (handoff) ---
        # Si un agente tomó la conversación (atendido_por=humano), el bot queda en
        # SILENCIO total: no responde menú ni LLM. La única excepción es el flujo de
        # validación que el propio agente disparó (esperando_cedula/telefono/otp),
        # para que cédula/OTP/SMS sigan funcionando sin duplicar lógica. El mensaje
        # entrante ya fue persistido por el webhook/web_chat, así que el panel del
        # agente lo verá al refrescar.
        atendido = redisdb.get_variable(numero, "atendido_por")
        en_validacion = estado in (b"esperando_cedula", b"esperando_telefono", b"esperando_otp")
        if atendido == b"humano" and not en_validacion:
            logg(f"procesar: conversación atendida por humano, bot en silencio (estado={estado})")
            return

        # --- Menú interactivo (WhatsApp y webchat) ---
        if canal in ("wa", "wc"):
            # Palabra clave: el usuario pide volver al menú principal
            if mensaje_original.lower() in ("menu", "menú", "inicio", "menu principal"):
                # Si el usuario ya está validado, no eliminar ese estado al abrir el menú
                try:
                    if estado != b"validado":
                        redisdb.del_variable(numero, "estado_validacion")
                except Exception:
                    # Si hay cualquier error leyendo/interpretando el estado, borrar por seguridad
                    redisdb.del_variable(numero, "estado_validacion")

                # Limpiar intent/pregunta pendiente (mantener cod_persona si ya estaba validado)
                redisdb.del_variable(numero, "intencion_pendiente")
                redisdb.del_variable(numero, "pregunta_original")
                redisdb.set_variable(numero, "menu_mostrado", "1")
                enviar_menu(canal, message_id, numero, "raiz")
                try:
                    # Registrar que el usuario abrió el menú
                    guardar_interaccion(numero, 0, canal, "menu", None, "Menu mostrado: raiz")
                except Exception as e:
                    loge(f"Error guardando interacción de menu: {e}")
                return
            # Selección desde un botón/list (WA entrega payload por Zenvia, webchat lo envía en el POST)
            if payload:
                tipo_pl, valor_pl = menu.resolver_payload(payload)
                if tipo_pl == "MENU":
                    enviar_menu(canal, message_id, numero, valor_pl)
                    try:
                        # Registrar navegación de menú (selección de lista)
                        guardar_interaccion(numero, 0, canal, payload, None, f"Menu mostrado: {valor_pl}")
                    except Exception as e:
                        loge(f"Error guardando interacción de menu (payload MENU): {e}")
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
                        result = {"intent": intent_pre, "type": "general", "entity": entities, "context": contexto, "intent_source": "menu"}
                    else:
                        result = process_query(pregunta_pre)
                        if intent_pre:
                            result["intent"] = intent_pre
                            result["intent_source"] = "menu"
                        contexto = result.get("context")
                    respuesta = menu.formatear_contexto_general(contexto)
                    if not respuesta:
                        respuesta = "No encontré información para esa opción. Escribe *menu* para volver al menú principal."
                    enviar_respuesta(canal, message_id, numero, respuesta)
                    guardar_interaccion(numero, 0, canal, pregunta_pre, result, respuesta)
                    return
                if tipo_pl == "TEL":
                    # Selección de teléfono para enviar el OTP
                    try:
                        idx = int(valor_pl)
                    except (ValueError, TypeError):
                        idx = 0
                    telefonos_b = redisdb.get_variable(numero, "telefonos_otp")
                    cod_persona_b = redisdb.get_variable(numero, "cod_persona")
                    nombres_b = redisdb.get_variable(numero, "nombres")
                    saludo_b = redisdb.get_variable(numero, "saludo_otp")
                    if telefonos_b and cod_persona_b:
                        telefonos = json.loads(telefonos_b.decode())
                        cod_persona = cod_persona_b.decode()
                        nombres = nombres_b.decode() if nombres_b else ""
                        saludo = saludo_b.decode() if saludo_b else "Bienvenido/a"
                        if 0 <= idx < len(telefonos):
                            celular_elegido = telefonos[idx]
                        else:
                            celular_elegido = telefonos[0]
                        redisdb.del_variable(numero, "telefonos_otp")
                        redisdb.del_variable(numero, "saludo_otp")
                        redisdb.set_variable(numero, "estado_validacion", "esperando_otp")
                        otp = str(randint(100000, 999999))
                        redisdb.set_variable(numero, "otp", otp, expira=300)
                        logg(f"OTP generado para {cod_persona} -> tel idx={idx}: {otp}")
                        sms = f"Este es el código de verificación para validar tu identidad con Real[IA]: {otp}"
                        pid = envia_sms(celular_elegido, sms)
                        cel4d = celular_elegido[-4:]
                        if pid > 0:
                            respuesta = f"¡{saludo} {nombres}! Te he enviado un código de verificación al número terminado en XXX-XXX-{cel4d}. Por favor indícame el código que recibiste."
                        else:
                            respuesta = f"No fue posible enviar el código al número terminado en {cel4d}. Por favor pasa por una sucursal a corregir tus datos."
                        enviar_respuesta(canal, message_id, numero, respuesta)
                    else:
                        enviar_respuesta(canal, message_id, numero,
                            "Tu sesión expiró. Escribe *menu* para comenzar de nuevo.")
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
                            result["intent_source"] = "menu"
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
                            "Para ayudarte, necesito validar tu identidad. Por favor dame tu número de cédula (sin guiones).")
                    return

        if len(mensaje_original) > 0 :
            # --- 1. Si está esperando cédula ---
            if estado == b"esperando_cedula":
                intencion_val = clasificar_intencion_validacion(mensaje_original)
                if intencion_val == "cancelar":
                    limpiar_estado_validacion(numero)
                    enviar_respuesta(canal, message_id, numero,
                        "Listo, cancelé la solicitud. Escribe *menu* para ver opciones") # o pregúntame otra cosa cuando quieras.
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
                        redisdb.set_variable(numero, "nombres", row["nombres"])
                        guardar_cliente(numero)
                        # Verificar si hay múltiples teléfonos registrados
                        telefonos = _parsear_telefonos(celular)
                        if len(telefonos) > 1:
                            # Guardar lista y pedir al cliente que elija
                            redisdb.set_variable(numero, "estado_validacion", "esperando_telefono")
                            redisdb.set_variable(numero, "telefonos_otp", json.dumps(telefonos))
                            redisdb.set_variable(numero, "saludo_otp", saludo)
                            enviar_menu_telefonos(canal, message_id, numero, saludo, nombres, telefonos)
                            return
                        # Un solo teléfono: proceder directamente
                        celular_elegido = telefonos[0] if telefonos else celular
                        redisdb.set_variable(numero, "estado_validacion", "esperando_otp")
                        # Generar OTP
                        otp = str(randint(100000, 999999))
                        redisdb.set_variable(numero, "otp", otp, expira=300)
                        logg(f"OTP generado para {cod_persona}: {otp}")
                        sms = f"Este es el código de verificación para validar tu identidad con Real[IA]: {otp}"
                        pid = envia_sms(celular_elegido, sms)
                        cel4d = celular_elegido[-4:]
                        if pid > 0:
                            respuesta = f"¡{saludo} {nombres}! Te he enviado un código de verificación a tu celular terminado en XXX-XXX-{cel4d}. Por favor indícame el código que recibiste."
                        else:
                            respuesta = f"No fue posible enviar un código de verificación OTP a tu celular terminado en {cel4d}. Por favor pase por una sucursal a corregir sus datos."
                    else:
                        respuesta = "No encontramos un cliente con esa cédula. Por favor, verifícala."
                        #enviar_respuesta(canal, message_id, numero, respuesta)
                else:
                    respuesta = ("Estoy esperando tu número de cédula (sin guiones).\n"
                                 "• Si quieres terminar, responde *cancelar*.\n")
                                 #"• Si prefieres hablar con una persona, responde *agente*.")

            # --- 2. Si está esperando selección de teléfono para OTP ---
            elif estado == b"esperando_telefono":
                intencion_val = clasificar_intencion_validacion(mensaje_original)
                if intencion_val == "cancelar":
                    limpiar_estado_validacion(numero)
                    enviar_respuesta(canal, message_id, numero,
                        "Listo, cancelé la solicitud. Escribe *menu* para ver opciones.")
                    return
                if intencion_val == "agente":
                    enviar_respuesta(canal, message_id, numero, mensaje_contacto_humano())
                    return
                # Aceptar "1", "2", etc. como selección
                telefonos_b = redisdb.get_variable(numero, "telefonos_otp")
                nombres_b = redisdb.get_variable(numero, "nombres")
                saludo_b = redisdb.get_variable(numero, "saludo_otp")
                cod_persona_b = redisdb.get_variable(numero, "cod_persona")                
                if not telefonos_b or not cod_persona_b:
                    limpiar_estado_validacion(numero)
                    enviar_respuesta(canal, message_id, numero,
                        "Tu sesión expiró. Escribe *menu* para comenzar de nuevo.")
                    return
                telefonos = json.loads(telefonos_b.decode())
                cod_persona = cod_persona_b.decode()
                nombres = nombres_b.decode() if nombres_b else ""
                saludo = saludo_b.decode() if saludo_b else "Bienvenido/a"
                # Interpretar selección
                idx = None
                if re.fullmatch(r"\d+", mensaje_original.strip()):
                    n = int(mensaje_original.strip())
                    if 1 <= n <= len(telefonos):
                        idx = n - 1
                if idx is None:
                    enviar_menu_telefonos(canal, message_id, numero, "Claro", nombres, telefonos)
                    return
                    # No se entendió, reenviar menú
                    #lista = "\n".join(f"{i+1}. XXX-XXX-{t[-4:]}" for i, t in enumerate(telefonos))
                    #enviar_respuesta(canal, message_id, numero,
                    #    f"Por favor elige a qué número enviar el código respondiendo con el número de la opción:\n{lista}\n• Para cancelar responde *cancelar*.")
                    #return
                celular_elegido = telefonos[idx]
                redisdb.del_variable(numero, "telefonos_otp")
                redisdb.del_variable(numero, "saludo_otp")
                redisdb.set_variable(numero, "estado_validacion", "esperando_otp")
                otp = str(randint(100000, 999999))
                redisdb.set_variable(numero, "otp", otp, expira=300)
                logg(f"OTP generado para {cod_persona} -> tel idx={idx}: {otp}")
                sms = f"Este es el código de verificación para validar tu identidad con Real[IA]: {otp}"
                pid = envia_sms(celular_elegido, sms)
                cel4d = celular_elegido[-4:]
                if pid > 0:
                    respuesta = f"¡{saludo} {nombres}! Te he enviado un código de verificación al número terminado en XXX-XXX-{cel4d}. Por favor indícame el código que recibiste."
                else:
                    respuesta = f"No fue posible enviar el código al número terminado en {cel4d}. Por favor pasa por una sucursal a corregir tus datos."

            # --- 3. Si está esperando OTP ---
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
                        #"• Si prefieres hablar con una persona, responde *agente*.\n"
                        "• Para terminar, responde *cancelar*.")
                    return
                otp_esperado = redisdb.get_variable(numero, "otp")
                if otp_esperado and mensaje_original == otp_esperado.decode():
                    message_id = redisdb.get_variable(numero, "message_id").decode()
                    redisdb.set_variable(numero, "estado_validacion", "validado")
                    redisdb.del_variable(numero, "otp")
                    # FASE 7: si la conversación está atendida por un humano, NO se
                    # ejecuta la intención original. Sólo se marca al cliente como
                    # validado y se notifica (el panel del agente lo refleja al
                    # refrescar /conversacion, que expone estado_validacion).
                    if redisdb.get_variable(numero, "atendido_por") == b"humano":
                        redisdb.set_variable(numero, "cliente_validado", "1")
                        cod_persona = (redisdb.get_variable(numero, "cod_persona") or b"").decode()
                        respuesta = "¡Validación exitosa!"
                        enviar_respuesta(canal, message_id, numero, respuesta)
                        guardar_interaccion(numero, cod_persona, canal, mensaje, None, respuesta)
                        return
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

            # --- 4. Si ya está validado ---
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
                

            # --- 5. Primer mensaje: detectar intención confidencial ---
            else:
                # Primer mensaje de la sesión (estado vacío): mostrar siempre el menú raíz,
                # sin importar el contenido. La bandera 'menu_mostrado' evita repetirlo
                # en mensajes siguientes hasta que expire el hash de sesión (~10 min).
                if canal in ("wa", "wc") and not payload and not redisdb.get_variable(numero, "menu_mostrado"):
                    redisdb.set_variable(numero, "menu_mostrado", "1")
                    enviar_menu(canal, message_id, numero, "raiz")
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
                    respuesta = "Para ayudarte mejor, necesito validar tu identidad. Por favor dame tu número de cédula (sin guiones)."
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
    logg(f"enviar_respuesta:- canal: '{canal}', message_id: '{message_id}', numero: '{numero}'")
    guardar_mensaje(
        session_id=message_id,
        telefono=numero,
        canal=canal,
        direccion="OUT",
        contenido=respuesta
    )
    if canal == "wa":
        enviar_respuesta_wa(message_id, numero, respuesta)
    elif canal == "wc":
        enviar_respuesta_web(message_id, numero, respuesta)


def enviar_encuesta(canal, message_id, numero):
    """Enviar encuesta (solo WhatsApp) — misma firma que enviar_respuesta.

    Busca información en Redis (cliente_id, nombres, telefono) asociada a la clave
    `numero` (se usa el número de teléfono como clave en muchos flujos). Construye
    el payload requerido por el servicio de encuestas y, si recibe `url`, envía
    la URL por WhatsApp reutilizando `enviar_respuesta_wa`.
    """
    logg(f"enviar_encuesta:- canal: '{canal}', message_id: '{message_id}', numero: '{numero}'")
    if canal != "wa":
        logg("enviar_encuesta: canal no es 'wa', omitiendo")
        return

    try:
        # Intentar leer datos desde Redis usando el número como clave
        cliente_b = redisdb.get_variable(numero, "cliente_id")
        nombres_b = redisdb.get_variable(numero, "nombres")
        telefono_b = redisdb.get_variable(numero, "telefono") or redisdb.get_variable(numero, "celular")

        cliente = cliente_b.decode() if isinstance(cliente_b, (bytes, bytearray)) else (str(cliente_b) if cliente_b else "")
        nombres = nombres_b.decode() if isinstance(nombres_b, (bytes, bytearray)) else (str(nombres_b) if nombres_b else "")
        telefono = telefono_b.decode() if isinstance(telefono_b, (bytes, bytearray)) else (str(telefono_b) if telefono_b else numero)

        payload = {
            "cliente": cliente or "",
            "transaction": numero,
            "customer_phone": telefono or numero,
            "customer_name": nombres or "",
            "survey_id": ENCUESTA_ID
        }

        headers = {"Content-Type": "application/json"}
        if ENCUESTA_API_KEY:
            headers["X-API-Key"] = ENCUESTA_API_KEY

        logg(f"enviar_encuesta: llamando a {ENCUESTA_URL} payload={payload}")
        r = requests.post(ENCUESTA_URL, json=payload, headers=headers, timeout=10, verify=False)
        if r.status_code != 200:
            loge(f"enviar_encuesta: error status {r.status_code} -> {r.text}")
            return
        j = r.json()
        url = j.get("url") if isinstance(j, dict) else None
        if not url:
            loge(f"enviar_encuesta: no se devolvió 'url' en la respuesta: {j}")
            return

        texto = f"Por favor califica tu experiencia: {url} \nGracias por tu tiempo."
        enviar_respuesta_wa(message_id, numero, texto)
        logg(f"enviar_encuesta: encuesta enviada a {numero}")

    except Exception as e:
        loge(f"enviar_encuesta: excepción: {e}")


def _redis_expired_event_listener():
    """Listener que suscribe a eventos de expiración en Redis y actúa.

    Escucha en el canal __keyevent@0__:expired y, cuando una clave con
    prefijo conocido (p.ej. 'chat:' o 'push:') expira, invoca el envío de
    la encuesta. Corre en un hilo daemon.
    """
    try:
        r = redisdb.getRedis()
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        # Suscribirse al canal de eventos de expiración en la DB 0
        channel = "__keyevent@0__:expired"
        pubsub.subscribe(channel)
        logg(f"_redis_expired_event_listener: suscrito a {channel}")
        for msg in pubsub.listen():
            try:
                if not msg:
                    continue
                data = msg.get('data')
                if not data:
                    continue
                if isinstance(data, bytes):
                    key = data.decode('utf-8')
                else:
                    key = str(data)
                logg(f"_redis_expired_event_listener: expired key='{key}'")
                # Manejar claves conocidas
                if key.startswith('chat:'):
                    session_id = key.split(':', 1)[1]
                    # Intentar enviar encuesta por push/WA para session
                    try:
                        Thread(target=_send_survey_for_session, args=(session_id,), daemon=True).start()
                    except Exception as e:
                        loge(f"Error lanzando _send_survey_for_session: {e}")
                elif key.startswith('push:'):
                    session_id = key.split(':', 1)[1]
                    try:
                        Thread(target=_send_survey_for_session, args=(session_id,), daemon=True).start()
                    except Exception as e:
                        loge(f"Error lanzando _send_survey_for_session desde push: {e}")
                elif key.startswith('phone:') or key.startswith('wa:'):
                    # Si usas un patrón para keys por telefono
                    telefono = key.split(':', 1)[1]
                    try:
                        Thread(target=_send_survey_for_phone, args=(telefono,), daemon=True).start()
                    except Exception as e:
                        loge(f"Error lanzando _send_survey_for_phone: {e}")
            except Exception as inner:
                loge(f"_redis_expired_event_listener inner error: {inner}")
    except Exception as e:
        loge(f"_redis_expired_event_listener error: {e}")


# Arrancar listener de expiraciones en un hilo daemon
try:
    Thread(target=_redis_expired_event_listener, daemon=True).start()
except Exception as e:
    loge(f"No se pudo iniciar el listener de expiraciones Redis: {e}")

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
     # Convertir formato WhatsApp (*bold*, _italic_, ~strike~, `code`) a HTML
    def _wa_to_html(text):
        try:
            import html as _html
            if text is None:
                return ""
            s = _html.escape(str(text))
            # code blocks `code`
            s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
            # bold *text*
            s = re.sub(r'\*(?P<t>[^*]+)\*', r'<strong>\g<t></strong>', s)
            # italic _text_
            s = re.sub(r'_(?P<t>[^_]+)_', r'<em>\g<t></em>', s)
            # strikethrough ~text~
            s = re.sub(r'~(?P<t>[^~]+)~', r'<s>\g<t></s>', s)
            # preserve newlines
            s = s.replace('\n', '<br>')
            return s
        except Exception as e:
            loge(f"_wa_to_html: error formateando texto: {e}")
            return str(text) if text is not None else ""
    logg("Convirtiendo formato WhatsApp a HTML")
    respuesta_html = _wa_to_html(respuesta)
    redisdb.add_web_message(session_id, message_id, respuesta_html)
    notify(session_id, respuesta_html)

def enviar_menu_web(message_id, session_id, menu_id):
    """Envía un menú interactivo al webchat. Se serializa como JSON con type='menu'
    para que el cliente lo renderice como botones."""
    m = menu.get_menu(menu_id)
    if not m:
        logg(f"enviar_menu_web: menú '{menu_id}' no encontrado")
        return
    payload = {
        "message_id": message_id,
        "type": "menu",
        "menu_id": menu_id,
        "menu": {
            "header": m.get("header") or "",
            "body":   m.get("body") or "",
            "footer": m.get("footer") or "",
            "button": m.get("button") or "Ver opciones",
            "sections": m.get("sections") or [],
        },
    }
    rdb = redisdb.getRedis()
    rdb.rpush(f"mensajes:{session_id}", json.dumps(payload, ensure_ascii=False))
    notify(session_id, m.get("body") or "Menú disponible")

def enviar_menu(canal, message_id, numero, menu_id):
    """Dispatcher de menú según canal."""
    if canal == "wa":
        enviar_menu_wa(message_id, numero, menu_id)
    elif canal == "wc":
        enviar_menu_web(message_id, numero, menu_id)

def mensaje_redirigir_menu():
    """Mensaje que se envía cuando USE_LLM=false y la conversación entra en una rama
    que normalmente iría al LLM. Redirige al usuario al menú o al teléfono."""
    tel = _telefono_cooperativa()
    base = ("En este momento puedo ayudarte mejor a través del menú. "
            "Por favor escribe *menu* para ver todas las opciones disponibles.")
    if tel:
        base += f"\nSi prefieres hablar con una persona, llámanos al {tel}."
    return base

def llamada_llm(session_id, intencion, pregunta, contexto_str, is_payload = False):
    if not USE_LLM:
        logg(f"llamada_llm: LLM deshabilitado (USE_LLM=false). intent='{intencion}' q='{pregunta}' -> redirige a menú")
        return mensaje_redirigir_menu()
    try:
        logg(f"llamada_llm: Inicio '{intencion}' '{pregunta}'\r\n{contexto_str}")
        inicio = time.time()
        chat = ConversationManager(session_id)
        conversacion = json.dumps(chat.get_conversation_history(), ensure_ascii=False)
        conocimiento_extra = ""
        if not str(contexto_str).strip():
            conocimiento_extra = load_jsonl_from_file("context_cvr.jsonl")

        respuesta = preguntar_llm(intencion, pregunta, contexto_str, conversacion, conocimiento_extra, max_reintentos=2, modelo=OLLAMA_MODEL, endpoint=OLLAMA_URL, is_payload = is_payload)
        respuesta = respuesta.strip()
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
    conocimiento = load_jsonl_from_file('context_cvr.json')
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
                   "no llego", "no me ha llegado",
                   "mandalo de nuevo", "envialo de nuevo", "manda otro",
                   "envia otro")
    if any(k in t for k in kw_reenviar):
        return "reenviar"
    return None

def limpiar_estado_validacion(numero):
    """Limpia las variables del flujo de validación de identidad."""
    for campo in ("estado_validacion", "intencion_pendiente", "pregunta_original",
                  "message_id", "modo", "otp", "telefonos_otp", "saludo_otp"):
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


def _parsear_telefonos(celular_str):
    """Parsea 'CELULAR,TELEFONO' y retorna lista de números válidos únicos (solo dígitos, mín 7 chars)."""
    if not celular_str:
        return []
    vistos = set()
    result = []
    for t in celular_str.split(','):
        t = t.strip().replace('-', '').replace(' ', '').replace('+', '').replace('.', '')
        if t and len(t) >= 7 and t not in vistos:
            vistos.add(t)
            result.append(t)
    return result


def enviar_menu_telefonos(canal, message_id, numero, saludo, nombres, telefonos):
    """Envía menú dinámico para que el cliente seleccione a qué número enviar el OTP."""
    header = "Selección de teléfono"
    body = f"¡{saludo} {nombres}! ¿A qué número deseas que te enviemos el código de verificación?"
    rows = [{"id": f"TEL:{i}", "title": f"XXX-XXX-{tel[-4:]}"} for i, tel in enumerate(telefonos)]

    if canal == "wa":
        contenido = {
            "type": "list",
            "header": header[:60],
            "body": body[:1024],
            "button": "Seleccionar número",
            "sections": [{"title":"Teléfonos","rows": rows}],
        }
        payload = {
            "externalId": "realia",
            "from": ZENVIA_WANUMBER,
            "to": numero,
            "contents": [contenido],
        }
        response = requests.post(ZENVIA_API, json=payload, headers=ZENVIA_HEADERS, verify=False)
        if response.status_code != 200:
            logg(f"enviar_menu_telefonos WA: {response.status_code}")
           
            logg(f"enviar_menu_wa:\r\n=======INICIO RESPUESTA============\r\n{response.text}\r\n=========FIN RESPUESTA==========")
    elif canal == "wc":
        menu_payload = {
            "message_id": message_id,
            "type": "menu",
            "menu_id": "_tel_otp",
            "menu": {
                "header": header,
                "body": body,
                "footer": "",
                "button": "Seleccionar",
                "sections": [{"title": "Teléfonos registrados", "rows": rows}],
            },
        }
        rdb = redisdb.getRedis()
        rdb.rpush(f"mensajes:{numero}", json.dumps(menu_payload, ensure_ascii=False))
        notify(numero, body)


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
                "context": None,
                "intent_source": None,
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

        # Fallback LLM: si reglas no clasificaron (intent=general), pedir al LLM
        # que elija un intent. Luego re-corremos extract_entities con ese intent.
        # Sólo para consultas libres (saludo/cierre ya tienen su path).
        intent_source = "regla"
        if intent in (None, 'general') and not es_saludo(query) and not es_cierre(query):
            llm_intent, _ = detect_intent_llm(query)
            if llm_intent and llm_intent != 'general':
                intent = llm_intent
                intent_source = "llm"
                local_entities = extract_entities(intent, query) or local_entities

        if intent == "saldo":
            tipo = "personal"
        result["intent"] = intent
        result["type"] = tipo
        result["entity"] = local_entities
        result["intent_source"] = intent_source
        logg(f"process_query: intent type '{tipo}' intent='{intent}' source={intent_source} entities='{local_entities}'")
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
    # Reemplazar sinónimos respetando límites de palabra (evita que 'entrega' rompa 'entregado').
    synonyms = load_json_from_file('synonyms.json')
    for syn, main in synonyms.items():
        text = re.sub(r'\b' + re.escape(syn) + r'\b', main, text)
    return text.strip()

# Cache de archivos de configuración (intents, entities, context, synonyms, plantillas, ...).
# Re-lee desde disco solo cuando cambia el mtime del archivo.
_file_cache = {}  # full_path -> (mtime, data)


def _cached_read(filepath, parser):
    full_path = f"{filepath}"
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
    json_path = os.path.join(BASE_PATH, "json", filepath)
    return _cached_read(json_path, _parse_json)


def load_jsonl_from_file(filepath) -> dict:
    jsonl_path = os.path.join(BASE_PATH, "json", filepath)
    return _cached_read(jsonl_path, _parse_jsonl)

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


def _intents_validos():
    """Set de intents válidos según intents.json."""
    j = load_json_from_file('intents.json') or {}
    return set(j.keys())

def _rutas_validas():
    """Set de rutas válidas (tipo/subtipo/valor) según entities.jsonl."""
    ents = load_jsonl_from_file('entities.jsonl') or []
    out = set()
    for it in ents:
        r = it.get('ruta')
        if r:
            out.add(r)
        t, s, v = it.get('tipo'), it.get('subtipo'), it.get('valor')
        if t and s and v:
            out.add(f"{t}/{s}/{v}")
    return out

_INTENT_HINTS = {
    'empresa':   'historia, misión, visión, valores, filosofía, contacto, estructura, políticas, cómo afiliarse',
    'producto':  'cuentas, préstamos, certificados, tarifas, membresías, electrodomésticos, vehículos, paneles solares, agropecuarios',
    'servicio':  'plan farmacia, plan odontológico, plan funeral, consultorio, casa club, educación, recreación, salud',
    'sucursal':  'oficinas, direcciones, ubicaciones de las sucursales, horarios',
    'actividad': 'eventos, talleres, charlas, jornadas, celebraciones',
    'saldo':     'consultas personales del cliente: mis cuentas, mis préstamos, mis certificados, mi pedido de la feria, dónde está mi orden',
    'ayuda':     'precios de la feria, bloqueo de tarjeta, internet banking, cómo hago algo, información general',
    'empleo':    'vacantes, oportunidades de empleo',
    'saludo':    'hola, buenos días, qué tal',
}

def detect_intent_llm(query: str):
    """Fallback de detección de intent vía LLM cuando reglas no clasifican.
    El LLM SOLO elige el intent (lista corta); la extracción de entities sigue
    siendo determinista vía extract_entities. Cacheado 5 min en Redis.
    Retorna (intent, []) o (None, []) si falla."""
    if not USE_LLM:
        return None, []
    if not query or not query.strip():
        return None, []
    q_norm = normalize_text(query)
    cache_key = f"intent_llm:{hashlib.md5(q_norm.encode('utf-8')).hexdigest()}"
    rdb = redisdb.getRedis()
    try:
        cached = rdb.get(cache_key)
        if cached:
            return json.loads(cached).get('intent'), []
    except Exception:
        pass

    intents_validos = _intents_validos()
    if not intents_validos:
        return None, []

    hints = "\n".join(
        f"- {k}: {v}" for k, v in _INTENT_HINTS.items() if k in intents_validos
    )
    prompt = (
        "Eres un clasificador de intents. NO conversas, sólo respondes JSON.\n\n"
        "Intents disponibles (con ejemplos):\n" + hints + "\n\n"
        f'Mensaje del usuario: "{query}"\n\n'
        "Responde SOLO con un objeto JSON con esta forma EXACTA, sin texto adicional, "
        "sin Markdown, sin explicaciones:\n"
        '{"intent":"<uno_de_los_intents>"}\n\n'
        'Si ninguno encaja claramente, usa "general".'
    )

    try:
        respuesta = llama_openai(OLLAMA_URL, OLLAMA_MODEL, prompt) or ""
        m = re.search(r'\{[^{}]*"intent"[^{}]*\}', respuesta, re.DOTALL)
        if not m:
            logg(f"detect_intent_llm: respuesta sin JSON parseable: {respuesta[:200]}")
            return None, []
        data = json.loads(m.group(0))
        intent = (data.get('intent') or '').strip().lower()
        if intent not in intents_validos:
            intent = 'general'
        try:
            rdb.setex(cache_key, 300, json.dumps({'intent': intent}))
        except Exception as e:
            loge(f"detect_intent_llm: error cacheando: {e}")
        logg(f"detect_intent_llm: '{query}' -> intent='{intent}'")
        return intent, []
    except Exception as e:
        loge(f"detect_intent_llm: error consultando LLM: {e}")
        return None, []


def _stem_es(w):
    """Stemmer mínimo para tolerar plurales en español.
    - 'materiales' -> 'material', 'paneles' -> 'panel' (consonante + 'es').
    - 'agropecuarios' -> 'agropecuario', 'motocicletas' -> 'motocicleta', 'viajes' -> 'viaje' (vocal + 's').
    Aplica con longitud mínima para evitar sobre-stem."""
    if len(w) > 4 and w.endswith('es') and w[-3] not in 'aeiouáéíóú':
        return w[:-2]
    if len(w) > 3 and w.endswith('s'):
        return w[:-1]
    return w

def extract_entities(intent, query: str) -> Dict:
    query = normalize_text(query)
    logg(f"extract_entities('{intent}', '{query}')")
    found = []
    matchs = {}
    local_entities = load_jsonl_from_file('entities.jsonl')
    max_coincidencias = 0
    match_found = 0
    palabras_frase = {_stem_es(w) for w in query.split()}
    for item in local_entities:
        if intent != item.get("tipo"):
            continue
        # Construir palabras_clave UNA sola vez por item: dedup + stemming + split por '/' y '_'.
        palabras_clave = set()
        for v in item.values():
            if not isinstance(v, str):
                continue
            for w in v.lower().replace('_', ' ').replace('/', ' ').split():
                palabras_clave.add(_stem_es(w))
        coincidencias = len(palabras_clave & palabras_frase)
        if coincidencias > 0 and coincidencias >= max_coincidencias:
            max_coincidencias = coincidencias
            matchs[match_found] = {"coincidencias": coincidencias, "entity": item}
            match_found += 1
            logg(f"extract_entities: {coincidencias} pts {sorted(palabras_clave & palabras_frase)} item={item}")
        # Camino paralelo (substring match) preservado para llenar 'found' cuando matchs venga vacío.
        for campo in ['tipo', 'subtipo', 'valor', 'nombre', 'descripcion', 'contenido', 'fecha', 'municipio', 'provincia', 'pais', 'telefonos', 'extensiones']:
            if campo not in item:
                continue
            try:
                campo_arr = normalize_text(str(item[campo])).split("_")
                for c in campo_arr:
                    if c and c in query:
                        found.append(item)
                        logg(f"extract_entities: {campo} found: {item} -> '{c}' in '{query}'")
            except AttributeError as e:
                loge(f"extract_entities: Error {e}")
    if matchs:
       # Determinar la coincidencia máxima
        max_coincidencias = max(item['coincidencias'] for item in matchs.values())
        # Filtrar todos los objetos con la coincidencia máxima
        mejores_objetos = [item['entity'] for item in matchs.values() if item['coincidencias'] == max_coincidencias]
        
        objetos_sin_duplicados = []
        objetos_vistos = set()

        for obj in mejores_objetos:
            # Convertir valores no hashables (listas) a tuplas para poder dedupear.
            obj_tuple = tuple(sorted(
                (k, tuple(v) if isinstance(v, list) else v) for k, v in obj.items()
            ))
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
            "stream": False,
            "keep_alive": "30m"
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
        "keep_alive": "30m",
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
# Admin: login + interacciones
from werkzeug.security import check_password_hash
import csv
import io

ADMIN_USER = os.getenv("ADMIN_USER")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
AST_TZ = timezone(timedelta(hours=-4))

def _fmt_ast(ts_str):
    """Convierte timestamp SQLite (UTC) a 'DD/MM/YYYY hh:mm:ss AM/PM' AST (GMT-4).
    Implementación manual para evitar %p vacío con locale es_DO."""
    if not ts_str:
        return ''
    try:
        dt = datetime.strptime(str(ts_str)[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        d = dt.astimezone(AST_TZ)
        h12 = d.hour % 12 or 12
        ampm = 'AM' if d.hour < 12 else 'PM'
        return f"{d.day:02d}/{d.month:02d}/{d.year} {h12:02d}:{d.minute:02d}:{d.second:02d} {ampm}"
    except (ValueError, TypeError):
        return str(ts_str)

def _label_cliente(v):
    """Etiqueta del cliente para vista admin: 'Cliente <num>' o 'Cliente N/D' si es 0/None."""
    if v in (None, '', '0', 0):
        return 'Cliente N/D'
    return f'Cliente {v}'


def _require_login():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return None



def _csv_celda(v):
    """Normaliza un valor para una celda CSV: colapsa saltos de línea a espacio.

    csv.writer ya escapa comas/comillas encerrando el campo entre comillas,
    pero los saltos de línea embebidos confunden a algunos lectores (Excel).
    """
    if v is None:
        return ''
    return ' '.join(str(v).replace('\r\n', '\n').replace('\r', '\n').split('\n')).strip()


def _parse_plantilla_row(r, notif_map=None):
    """Parsea una fila de obtener_respuestas_plantilla a dict listo para la vista.
    r: (id, fecha_hora, session_id, cod_persona, canal, pregunta, intencion, respuesta)

    Si se pasa `notif_map` (dict {destino: detalle} obtenido por lote con
    buscar_notificaciones_por_destinos), NO se consulta Oracle por fila: se
    resuelve la notificación desde el mapa. Si es None se mantiene el
    comportamiento anterior (una consulta a Oracle por fila).
    """
    intent_data = {}
    id = 0
    try:
        numero = r[2]
        if notif_map is not None:
            detalle = notif_map.get(numero)
            if not detalle:
                return {}
        else:
            logg(f"_manejar_respuesta_plantilla: sin caché, consultando Oracle para {numero}")
            matches = buscar_notificaciones_por_destino(numero, tipo_notificacion=2, limit=1)
            if not matches:
                return {}
            detalle = matches[0].get('detalle')
        #logg(f"detalle: {json.dumps(detalle, ensure_ascii=False, indent=2)}")
        try:
            id = detalle.get('id')
            intent_data = detalle.get('contents')[0]
        except Exception:
            return {}
        #logg(f"intent_data: {json.dumps(intent_data, ensure_ascii=False, indent=2)}")

    except (TypeError, ValueError):
        pass
    
    fields = intent_data.get('fields') or {}
    url = (fields.get('url') or fields.get('link') or
           fields.get('enlace') or fields.get('URL') or '')
    nombre = fields.get('nombre', '')
    descripcion = (fields.get('nombre_evento') or fields.get('consejos') or
                   fields.get('accion') or fields.get('asunto') or '')
    return {
        'id': r[0],
        'fecha': _fmt_ast(r[1]),
        'telefono': r[2],
        'nombre': nombre,
        'descripcion': descripcion,
        'url': url,
        'mensaje': r[5],
        'template_id': intent_data.get('templateId') or '',
        'outgoing_msg_id': intent_data.get('outgoing_msg_id') or '',
        'fields_json': json.dumps(fields, ensure_ascii=False, indent=2) if fields else '',
    }


@app.route('/respuestas-plantilla')
def respuestas_plantilla():
    if (resp := _require_login()) is not None:
        return resp
    f = _filtros_request(request)
    try:
        pagina = max(1, int(request.args.get('p', 1)))
    except ValueError:
        pagina = 1
    try:
        por_pagina = int(request.args.get('pp', 50))
    except ValueError:
        por_pagina = 50

    filas_raw, total = obtener_respuestas_plantilla(
        desde=f['desde'], hasta=f['hasta'], q=f['q'],
        pagina=pagina, por_pagina=por_pagina,
    )
    filas = []

    notif_map = buscar_notificaciones_por_destinos(
        [r[2] for r in filas_raw], tipo_notificacion=2)
    for r in filas_raw:
        fila = _parse_plantilla_row(r, notif_map)
        if fila:
            filas.append(fila)
    con_url = sum(1 for r in filas if r['url'])
    sin_url = len(filas) - con_url

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    desde_idx = 0 if total == 0 else (pagina - 1) * por_pagina + 1
    hasta_idx = min(total, pagina * por_pagina)

    return render_template(
        'plantillas.html',
        usuario=session.get('usuario'),
        filas=filas, total=total,
        stats={'con_url': con_url, 'sin_url': sin_url},
        total_paginas=total_paginas,
        pagina=pagina, desde_idx=desde_idx, hasta_idx=hasta_idx,
        filtros={**f, 'por_pagina': por_pagina},
    )


@app.route('/respuestas-plantilla/csv')
def respuestas_plantilla_csv():
    if (resp := _require_login()) is not None:
        return resp
    f = _filtros_request(request)
    filas_raw, _total = obtener_respuestas_plantilla(
        desde=f['desde'], hasta=f['hasta'], q=f['q'],
        pagina=1, por_pagina=50000,
    )
    buf = io.StringIO()
    buf.write('\ufeff')
    # QUOTE_ALL: encierra todos los campos entre comillas para que comas,
    # punto y coma o saltos de l\u00ednea dentro del mensaje no rompan columnas.
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    #w.writerow([
    #    'fecha_recibido', 'telefono', 'nombre', 'descripcion',
    #    'url', 'mensaje_cliente', 'templateId', 'outgoing_msg_id', 'fields_completo',
    #])
    w.writerow([
        'fecha_recibido', 'telefono', 'nombre','descripcion', 'template_id',  'mensaje_cliente',
    ])
    notif_map = buscar_notificaciones_por_destinos(
        [r[2] for r in filas_raw], tipo_notificacion=2)
    for r in filas_raw:
        d = _parse_plantilla_row(r, notif_map)
        if d:
            w.writerow([
                d['fecha'], d['telefono'], d['nombre'], d['descripcion'],
                d['template_id'], _csv_celda(d['mensaje']),
            ])
            #w.writerow([
            #    d['fecha'], d['telefono'], d['nombre'], d['descripcion'],
            #    d['url'], d['mensaje'], d['template_id'], d['outgoing_msg_id'], d['fields_json'],
            #])
    out = buf.getvalue()
    fname = f"respuestas_plantilla_{f['desde']}_{f['hasta']}.csv"
    return app.response_class(
        out, mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '')
        valido = False
        if (ADMIN_USER and ADMIN_PASSWORD_HASH
                and usuario == ADMIN_USER
                and check_password_hash(ADMIN_PASSWORD_HASH, password)):
                valido = True
        else:
            valido = validar_usuario(usuario, password)

        if valido:
            session['usuario'] = usuario
            return redirect(url_for('interacciones'))
        
        flash('Credenciales incorrectas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

def _filtros_request(req):
    """Lee filtros comunes desde request.args."""
    hoy = datetime.now(AST_TZ).strftime('%Y-%m-%d')
    return {
        'desde': req.args.get('desde') or hoy,
        'hasta': req.args.get('hasta') or hoy,
        'canal': req.args.get('canal') or None,
        'q':     (req.args.get('q') or '').strip() or None,
    }

def _stats_periodo(canal, desde, hasta, q):
    """Stats agregadas para el rango filtrado."""
    import sqlite3
    con = sqlite3.connect(os.getenv('SQLITE_DBNAME'))
    cur = con.cursor()
    where, params = [], []
    if canal:
        where.append('m.canal = ?'); params.append(canal)
    if desde:
        where.append('m.fecha_hora >= ?'); params.append(desde)
    if hasta:
        where.append("m.fecha_hora < datetime(?, '+1 day')"); params.append(hasta)
    if q:
        where.append('m.contenido LIKE ?')
        params.append(f'%{q}%')
    w = (' WHERE ' + ' AND '.join(where)) if where else ''
    cur.execute(
        f"SELECT COUNT(m.id), COUNT(DISTINCT c.id), "
        f"       SUM(CASE WHEN m.canal='wa' THEN 1 ELSE 0 END), "
        f"       SUM(CASE WHEN m.canal='wc' THEN 1 ELSE 0 END), "
        f"       COUNT(DISTINCT CASE WHEN c.cod_persona NOT IN ('0','','') AND c.cod_persona IS NOT NULL THEN c.cod_persona END) "
        f"FROM mensajes m JOIN conversaciones c ON c.id=m.conversacion_id{w}", params)
    row = cur.fetchone() or (0, 0, 0, 0, 0)
    con.close()
    return {
        'mensajes': row[0] or 0,
        'conversaciones': row[1] or 0,
        'wa': row[2] or 0,
        'wc': row[3] or 0,
        'clientes': row[4] or 0,
    }


@app.route('/interacciones')
def interacciones():
    if (resp := _require_login()) is not None:
        return resp

    f = _filtros_request(request)
    try:
        pagina = max(1, int(request.args.get('p', 1)))
    except ValueError:
        pagina = 1
    try:
        por_pagina = int(request.args.get('pp', 50))
    except ValueError:
        por_pagina = 50

    filas, total = obtener_conversaciones(
        canal=f['canal'], fecha_desde=f['desde'], fecha_hasta=f['hasta'],
        q=f['q'], pagina=pagina, por_pagina=por_pagina,
    )
    stats = _stats_periodo(f['canal'], f['desde'], f['hasta'], f['q'])

    # Preformatear cada conversación para la vista (fechas en AST 12h, label cliente).
    conversaciones = [
        {
            'conversacion_id': row[0],
            'session_id':      row[1],
            'canal':           row[2],
            'cliente':         _label_cliente(row[3]),
            'fecha_inicio':    _fmt_ast(row[4]),
            'fecha_fin':       _fmt_ast(row[5]),
            'mensajes':        row[6],
            'telefono':        (row[7] if row[2] != 'wc' else None),
        }
        for row in filas
    ]

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    desde_idx = 0 if total == 0 else (pagina - 1) * por_pagina + 1
    hasta_idx = min(total, pagina * por_pagina)

    return render_template(
        'dashboard.html',
        usuario=session.get('usuario'),
        conversaciones=conversaciones,
        stats=stats,
        total=total, total_paginas=total_paginas,
        pagina=pagina, desde_idx=desde_idx, hasta_idx=hasta_idx,
        filtros={**f, 'por_pagina': por_pagina},
    )


# ─── Helpers de atención humana (handoff) ─────────────────────────────────
def _norm_b(v):
    """Normaliza un valor de Redis (bytes/str/None) a str en minúsculas o ''."""
    if v is None:
        return ''
    if isinstance(v, (bytes, bytearray)):
        v = v.decode('utf-8', 'ignore')
    return str(v).strip().lower()

def _clave_redis(canal, session_id, telefono):
    """Clave usada en Redis por procesar(): session_id en web, teléfono en WhatsApp.
    Replica la convención existente (no introduce un esquema nuevo)."""
    if canal == 'wc':
        return session_id
    return telefono or session_id

def _label_estado_validacion(estado):
    """Traduce el estado_validacion de Redis a una etiqueta para el perfil:
    'Sin validar' | 'Validando' | 'Validado'."""
    e = _norm_b(estado)
    if e == 'validado':
        return 'Validado'
    if e in ('esperando_cedula', 'esperando_telefono', 'esperando_otp'):
        return 'Validando'
    return 'Sin validar'

def _nombre_cliente(cod_persona, clave=None):
    """Nombre del cliente: Oracle (buscar_cliente) o, en su defecto, el nombre
    guardado en Redis durante la validación."""
    nombre = ''
    if cod_persona and str(cod_persona) not in ('0', ''):
        try:
            datos = buscar_cliente(str(cod_persona))
            if datos and datos.get('nombres'):
                nombre = datos['nombres'].strip()
        except Exception as e:
            loge(f"_nombre_cliente: {e}")
    if not nombre and clave:
        nb = redisdb.get_variable(clave, "nombres")
        nombre = _norm_b(nb).title() if nb else ''
    return nombre

def _enviar_a_conversacion(header, texto, agente):
    """Persiste un mensaje OUT del agente en la conversación y lo entrega por el
    canal correspondiente. Reutilizado por /enviar y /atender (no duplica lógica)."""
    canal = header.get('canal')
    session_id = header.get('session_id')
    telefono = header.get('telefono')
    message_id = str(uuid.uuid4())
    if canal == 'wa' and not telefono:
        return False, 'sin_telefono'
    guardar_mensaje(
        session_id=session_id, canal=canal, direccion='OUT', contenido=texto,
        telefono=telefono, message_id=message_id, enviado_por=agente,
    )
    if canal == 'wa':
        enviar_respuesta_wa(message_id, telefono, texto)
    elif canal == 'wc':
        enviar_respuesta_web(message_id, session_id, texto)
    else:
        return False, 'canal_no_soportado'
    return True, message_id

def _contexto_personal(cod_persona, entities):
    """Construye el contexto de productos del cliente reutilizando contexto_cliente()
    y lo devuelve como (items_list, texto_formateado). NO duplica la lógica de Oracle."""
    query = {"intent": "consulta", "type": "personal", "entity": entities, "context": []}
    contexto = contexto_cliente(str(cod_persona), query)  # devuelve JSON string
    try:
        items = json.loads(contexto) if isinstance(contexto, str) else (contexto or [])
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []
    texto = menu.formatear_contexto_personal(contexto)
    return items, texto


@app.route('/interacciones/conversacion/<int:conversacion_id>')
def interaccion_conversacion(conversacion_id):
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    mensajes = obtener_mensajes_conversacion(conversacion_id)
    if not mensajes:
        return jsonify({'error': 'not_found'}), 404
    out = []
    canal = mensajes[0].get('canal')
    cod_persona = mensajes[0].get('cod_persona')
    session_id = mensajes[0].get('session_id')
    telefono = mensajes[0].get('telefono') or None
    for m in mensajes:
        metadata = None
        try:
            metadata = json.loads(m.get('metadata') or 'null')
        except (TypeError, ValueError):
            metadata = m.get('metadata')
        intencion = metadata.get('intencion') if isinstance(metadata, dict) else None
        # Teléfono: para canales no-web viene en el metadata del mensaje entrante (message.from).
        if not telefono and isinstance(metadata, dict):
            msg = metadata.get('message')
            if isinstance(msg, dict) and msg.get('from'):
                telefono = msg.get('from')
        adjunto = None
        if m.get('tiene_archivo'):
            adjunto = {
                'nombre': m.get('archivo_nombre'),
                'tipo': m.get('archivo_tipo'),
                'url': m.get('archivo_url'),
                'size': m.get('archivo_size'),
            }
        out.append({
            'id': m.get('id'),
            'fecha': m.get('fecha_hora'),
            'direccion': m.get('direccion'),
            'contenido': m.get('contenido'),
            'enviado_por': m.get('enviado_por'),
            'intencion': intencion,
            'intent_source': metadata.get('intent_source') if isinstance(metadata, dict) else None,
            'adjunto': adjunto,
        })

    # Estado de handoff/validación (Redis), para que el panel del agente refleje
    # en vivo si el cliente ya está validado o si el bot fue silenciado.
    atendido_por = mensajes[0].get('atendido_por') or 'bot'
    clave = _clave_redis(canal, session_id, telefono)
    estado_val = redisdb.get_variable(clave, "estado_validacion")
    cliente_validado = redisdb.get_variable(clave, "cliente_validado")
    adjuntos = [m['adjunto'] for m in out if m.get('adjunto')]
    return jsonify({
        'conversacion_id': conversacion_id,
        'session_id': session_id,
        'canal': canal,
        'cod_persona': cod_persona,
        'telefono': telefono if canal != 'wc' else None,
        'atendido_por': atendido_por,
        'estado_validacion': _norm_b(estado_val) or 'sin_validar',
        'estado_validacion_label': _label_estado_validacion(estado_val),
        'cliente_validado': bool(cliente_validado) or _norm_b(estado_val) == 'validado',
        'adjuntos': adjuntos,
        'mensajes': out,
    })


@app.route('/interacciones/conversacion/<int:conversacion_id>/enviar', methods=['POST'])
def interaccion_enviar(conversacion_id):
    """Envía un mensaje del agente dentro de una conversación existente y lo
    persiste como OUT (enviado_por = usuario de la sesión)."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    texto = (request.json or {}).get('texto', '') if request.is_json else request.form.get('texto', '')
    texto = (texto or '').strip()
    if not texto:
        return jsonify({'error': 'empty'}), 400

    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404

    agente = session.get('usuario')
    try:
        ok, ref = _enviar_a_conversacion(header, texto, agente)
    except Exception as e:
        loge(f"interaccion_enviar: error enviando mensaje: {e}")
        return jsonify({'error': 'send_failed', 'detalle': str(e)}), 500
    if not ok:
        return jsonify({'error': ref}), 400
    return jsonify({'ok': True, 'message_id': ref})


# ─── FASE 9: endpoints de atención humana y datos del cliente ───────────────
@app.route('/interacciones/conversacion/<int:conversacion_id>/atender', methods=['POST'])
def interaccion_atender(conversacion_id):
    """FASE 5: el agente inicia la atención humana.
      1. Marca atendido_por=humano (DB + Redis para que procesar() lo respete).
      2. Obtiene el nombre del agente con nombre_usuario().
      3. Envía automáticamente el saludo de presentación al cliente.
      5. (Frontend) habilita editor/enviar/adjuntar al recibir ok=True."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404

    canal = header.get('canal')
    session_id = header.get('session_id')
    telefono = header.get('telefono')
    cod_persona = header.get('cod_persona')
    usuario = session.get('usuario')
    clave = _clave_redis(canal, session_id, telefono)

    # Nombre del agente (Oracle); si falla, usar el usuario de la sesión.
    try:
        nombre_agente = nombre_usuario(usuario) or usuario
    except Exception as e:
        loge(f"interaccion_atender: nombre_usuario falló: {e}")
        nombre_agente = usuario

    # 1/4. Registrar atención humana (DB) y reflejarlo en Redis para procesar().
    marcar_atendido_por(conversacion_id, 'humano', asignado_a=usuario)
    redisdb.set_variable(clave, "atendido_por", "humano")

    # 3. Saludo automático de presentación.
    nombre_cliente = _nombre_cliente(cod_persona, clave)
    saludo = (f"Saludos {nombre_cliente}, le atiende {nombre_agente}."
              if nombre_cliente else f"Saludos, le atiende {nombre_agente}.")
    enviado = False
    try:
        enviado, ref = _enviar_a_conversacion(header, saludo, usuario)
    except Exception as e:
        loge(f"interaccion_atender: error enviando saludo: {e}")
        ref = 'send_failed'

    return jsonify({
        'ok': True,
        'atendido_por': 'humano',
        'agente': nombre_agente,
        'saludo': saludo,
        'saludo_enviado': bool(enviado),
        'saludo_error': None if enviado else ref,
    })


@app.route('/interacciones/conversacion/<int:conversacion_id>/identificar', methods=['POST'])
def interaccion_identificar(conversacion_id):
    """FASE 6: el agente pulsa "Solicitar cédula".
      1. Marca atendido_por=humano.
      2. Invoca el flujo de validación EXISTENTE poniendo estado=esperando_cedula
         y pidiendo la cédula. El cliente responderá y procesar() seguirá el flujo
         normal (cédula→OTP→SMS→validado) sin duplicar nada."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404

    canal = header.get('canal')
    session_id = header.get('session_id')
    telefono = header.get('telefono')
    usuario = session.get('usuario')
    clave = _clave_redis(canal, session_id, telefono)
    if canal == 'wa' and not telefono:
        return jsonify({'error': 'sin_telefono'}), 400

    message_id = str(uuid.uuid4())
    # 1. Atención humana.
    marcar_atendido_por(conversacion_id, 'humano', asignado_a=usuario)
    redisdb.set_variable(clave, "atendido_por", "humano")
    # 2. Preparar el flujo de validación existente (mismas variables que procesar()).
    redisdb.set_variable(clave, "estado_validacion", "esperando_cedula")
    redisdb.set_variable(clave, "intencion_pendiente", "")
    redisdb.set_variable(clave, "pregunta_original", "")
    redisdb.set_variable(clave, "message_id", message_id)
    redisdb.set_variable(clave, "modo", "menu")
    redisdb.del_variable(clave, "cliente_validado")

    prompt = ("Para continuar necesito validar tu identidad. "
              "Por favor indícame tu número de cédula (sin guiones).")
    try:
        ok, ref = _enviar_a_conversacion(header, prompt, usuario)
    except Exception as e:
        loge(f"interaccion_identificar: error: {e}")
        return jsonify({'error': 'send_failed', 'detalle': str(e)}), 500
    if not ok:
        return jsonify({'error': ref}), 400
    return jsonify({'ok': True, 'estado_validacion': 'esperando_cedula'})


@app.route('/interacciones/conversacion/<int:conversacion_id>/cliente')
def interaccion_cliente(conversacion_id):
    """FASE 10: perfil del cliente (Nombre, Código Persona, Teléfono, Canal,
    Estado de validación)."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404
    canal = header.get('canal')
    session_id = header.get('session_id')
    telefono = header.get('telefono')
    cod_persona = header.get('cod_persona')
    clave = _clave_redis(canal, session_id, telefono)
    estado_val = redisdb.get_variable(clave, "estado_validacion")
    return jsonify({
        'ok': True,
        'nombre': _nombre_cliente(cod_persona, clave) or 'N/D',
        'cod_persona': cod_persona if cod_persona not in (None, '', '0', 0) else 'N/D',
        'telefono': telefono or 'N/D',
        'canal': canal,
        'atendido_por': header.get('atendido_por') or 'bot',
        'estado_validacion': _norm_b(estado_val) or 'sin_validar',
        'estado_validacion_label': _label_estado_validacion(estado_val),
    })


def _datos_cliente_endpoint(conversacion_id, entities, etiqueta, filtro_subtipo=None, enviar=False):
    """Núcleo común de los endpoints de productos (cuentas/préstamos/certificados/feria).
    Exige que el cliente esté validado y reutiliza contexto_cliente().

    Si `enviar` es True, además de consultar, entrega el texto formateado
    directamente al cliente por su canal (reutiliza _enviar_a_conversacion, el
    mismo flujo que /enviar) y lo persiste como mensaje OUT del agente."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404
    cod_persona = header.get('cod_persona')
    canal = header.get('canal')
    clave = _clave_redis(canal, header.get('session_id'), header.get('telefono'))
    estado_val = _norm_b(redisdb.get_variable(clave, "estado_validacion"))
    if not cod_persona or str(cod_persona) in ('0', ''):
        return jsonify({'ok': False, 'error': 'cliente_no_identificado',
                        'mensaje': 'El cliente aún no se ha identificado.'}), 409
    if estado_val != 'validado':
        return jsonify({'ok': False, 'error': 'cliente_no_validado',
                        'mensaje': 'El cliente aún no completó la validación de identidad.'}), 409
    try:
        items, texto = _contexto_personal(cod_persona, entities)
    except Exception as e:
        loge(f"_datos_cliente_endpoint[{etiqueta}]: {e}")
        return jsonify({'ok': False, 'error': 'error_consulta', 'detalle': str(e)}), 500
    if filtro_subtipo:
        items = [it for it in items if (it.get('subtipo') or '').lower() in filtro_subtipo]

    if enviar:
        if not items or not (texto or '').strip():
            return jsonify({'ok': True, 'tipo': etiqueta, 'enviado': False,
                            'mensaje': f'No hay {etiqueta} para enviar al cliente.'})
        agente = session.get('usuario')
        try:
            ok_envio, ref = _enviar_a_conversacion(header, texto, agente)
        except Exception as e:
            loge(f"_datos_cliente_endpoint[{etiqueta}] enviar: {e}")
            return jsonify({'ok': False, 'error': 'send_failed', 'detalle': str(e)}), 500
        if not ok_envio:
            return jsonify({'ok': False, 'error': ref,
                            'mensaje': 'No se pudo enviar al cliente.'}), 400
        return jsonify({'ok': True, 'tipo': etiqueta, 'enviado': True,
                        'message_id': ref})

    return jsonify({'ok': True, 'tipo': etiqueta, 'items': items, 'texto': texto})


@app.route('/interacciones/conversacion/<int:conversacion_id>/cuentas', methods=['GET', 'POST'])
def interaccion_cuentas(conversacion_id):
    ents = [{"tipo": "producto", "subtipo": "cuenta", "valor": "cuentas"}]
    return _datos_cliente_endpoint(conversacion_id, ents, 'cuentas', filtro_subtipo={'cuenta'},
                                   enviar=(request.method == 'POST'))


@app.route('/interacciones/conversacion/<int:conversacion_id>/prestamos', methods=['GET', 'POST'])
def interaccion_prestamos(conversacion_id):
    ents = [{"tipo": "producto", "subtipo": "prestamo", "valor": "prestamos"}]
    return _datos_cliente_endpoint(conversacion_id, ents, 'prestamos',
                                   enviar=(request.method == 'POST'))


@app.route('/interacciones/conversacion/<int:conversacion_id>/certificados')
def interaccion_certificados(conversacion_id):
    # Los certificados se obtienen del mismo origen que las cuentas y se filtran
    # por subtipo (clasificación de _clasificar_producto_cuenta en rag_db).
    ents = [{"tipo": "producto", "subtipo": "cuenta", "valor": "certificados"}]
    return _datos_cliente_endpoint(conversacion_id, ents, 'certificados', filtro_subtipo={'certificado'})


@app.route('/interacciones/conversacion/<int:conversacion_id>/feria', methods=['GET', 'POST'])
def interaccion_feria(conversacion_id):
    ents = [{"tipo": "articulo", "subtipo": "prestamo_feria", "valor": "articulos"}]
    return _datos_cliente_endpoint(conversacion_id, ents, 'feria',
                                   enviar=(request.method == 'POST'))


# ─── Acciones adicionales del panel del agente (FASE 8) ─────────────────────
@app.route('/interacciones/conversacion/<int:conversacion_id>/nota', methods=['POST'])
def interaccion_nota(conversacion_id):
    """Nota interna del agente. No se entrega a ningún canal (direccion=NOTE)."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    texto = (request.json or {}).get('texto', '') if request.is_json else request.form.get('texto', '')
    texto = (texto or '').strip()
    if not texto:
        return jsonify({'error': 'empty'}), 400
    res = guardar_nota_interna(conversacion_id, session.get('usuario'), texto)
    if not res.get('ok'):
        return jsonify({'error': res.get('error', 'error')}), 404
    return jsonify({'ok': True, 'mensaje_id': res.get('mensaje_id')})


@app.route('/interacciones/conversacion/<int:conversacion_id>/transferir', methods=['POST'])
def interaccion_transferir(conversacion_id):
    """Reasigna la conversación a otro agente (mantiene atención humana)."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    destino = (request.json or {}).get('agente', '') if request.is_json else request.form.get('agente', '')
    destino = (destino or '').strip()
    if not destino:
        return jsonify({'error': 'empty'}), 400
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404
    transferir_conversacion(conversacion_id, destino)
    clave = _clave_redis(header.get('canal'), header.get('session_id'), header.get('telefono'))
    redisdb.set_variable(clave, "atendido_por", "humano")
    return jsonify({'ok': True, 'asignado_a': destino})


@app.route('/interacciones/conversacion/<int:conversacion_id>/cerrar', methods=['POST'])
def interaccion_cerrar(conversacion_id):
    """Cierra el caso y devuelve el control al bot (atendido_por=bot)."""
    if 'usuario' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    header = obtener_conversacion_header(conversacion_id)
    if not header:
        return jsonify({'error': 'not_found'}), 404
    cerrar_conversacion(conversacion_id)
    # Devolver el control al bot: limpiar Redis del handoff/validación.
    clave = _clave_redis(header.get('canal'), header.get('session_id'), header.get('telefono'))
    for var in ("atendido_por", "estado_validacion", "cliente_validado",
                "intencion_pendiente", "pregunta_original", "modo", "menu_mostrado"):
        redisdb.del_variable(clave, var)
    return jsonify({'ok': True, 'estado': 'CERRADA'})


@app.route('/interacciones/csv')
def interacciones_csv():
    if (resp := _require_login()) is not None:
        return resp
    f = _filtros_request(request)
    # Export sin paginar (hasta 50k filas como tope sano).
    columnas, filas, _total = obtener_interacciones(
        canal=f['canal'], fecha_desde=f['desde'], fecha_hasta=f['hasta'],
        q=f['q'], pagina=1, por_pagina=50000,
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['id','fecha_hora_ast','conversacion_id','session_id','cliente','canal','direccion','contenido','enviado_por','message_id','provider_message_id','template_id','metadata'])
    fh_idx = columnas.index('fecha_hora') if 'fecha_hora' in columnas else 1
    cp_idx = columnas.index('cod_persona')
    for r in filas:
        row = list(r)
        row[fh_idx] = _fmt_ast(row[fh_idx])
        row[cp_idx] = row[cp_idx] if row[cp_idx] not in (None,'','0',0) else 'N/D'
        w.writerow(row)
    out = buf.getvalue()
    fname = f"interacciones_{f['desde']}_{f['hasta']}.csv"
    return app.response_class(
        out, mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )

# ─── Puente desde plantillas → interacciones ──────────────────────────────

def _buscar_conversacion_reciente(session_id, canal='wa'):
    """Busca la conversación más reciente por session_id o teléfono."""
    import sqlite3
    con = sqlite3.connect(os.getenv('SQLITE_DBNAME'))
    cur = con.cursor()
    cur.execute(
        """
        SELECT c.id
        FROM conversaciones c
        WHERE c.canal = ?
          AND (c.session_id = ? OR c.telefono = ?)
        ORDER BY COALESCE(c.fecha_cierre, c.fecha_ultimo_mensaje, c.fecha_creacion) DESC, c.id DESC
        LIMIT 1
        """,
        (canal, session_id, session_id),
    )
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


@app.route('/interacciones/abrir')
def interacciones_abrir():
    """Puente desde plantillas hacia interacciones: redirige a la conversación más reciente."""
    if (resp := _require_login()) is not None:
        return resp
    sid = (request.args.get('session_id') or '').strip()
    canal = (request.args.get('canal') or 'wa').strip() or 'wa'
    if not sid:
        return redirect(url_for('interacciones', canal=canal))
    conv_id = _buscar_conversacion_reciente(sid, canal=canal)
    if conv_id:
        return redirect(url_for('interacciones', canal=canal, q=sid, open_conv=conv_id))
    return redirect(url_for('interacciones', canal=canal, q=sid))


@app.route('/interacciones/resolver')
def interacciones_resolver():
    """Resuelve session_id/teléfono → conversacion_id como JSON (para abrir modal en cualquier página)."""
    if (resp := _require_login()) is not None:
        return jsonify({'ok': False, 'error': 'no_auth'}), 401
    sid = (request.args.get('session_id') or '').strip()
    canal = (request.args.get('canal') or 'wa').strip() or 'wa'
    if not sid:
        return jsonify({'ok': False, 'error': 'session_id requerido'}), 400
    conv_id = _buscar_conversacion_reciente(sid, canal=canal)
    if conv_id:
        return jsonify({'ok': True, 'conv_id': conv_id})
    return jsonify({'ok': False, 'error': 'not_found'})


#######
if __name__ == "__main__":
    logg(f"api_llm: Usando modelo '{OLLAMA_MODEL}' en '{OLLAMA_URL}' (USE_LLM={USE_LLM})")
    logg(f"========================================================")
    app.run(host="0.0.0.0", port=8000, debug=True)
