#!/opt/rag/bin/python
import sys
import random
import whisper
import subprocess
import os
import time
import logging
import sys
import requests
import re
from asterisk.agi import AGI

# Configuración
LLM_ENDPOINT = "http://ragapi:8000"
TTS_SERVER = "http://tts.vegareal.local/tts"
VOICE_NAME = "Angelica"
CLIENTE_ID = "0"  # En producción se haría dinámico

headers = {
    "Authorization": "Bearer 91a732a744c0cf3f9e2651679d1ebd9055fee50e5132d2517a05cf3fe677daee"
}

logging.basicConfig(
    level = logging.INFO,
    format='[%(asctime)s] REALIA: %(message)s',
    stream=sys.stdout,
    datefmt='%Y-%m-%d %H:%M:%S' 
)

def logg(texto, nivel=1):
    str = f"({nivel}) {texto}"
    logging.info(str)

fullpath = f"/var/lib/asterisk/sounds"
savepath = "/opt/agi/app/sound"

def limpiar_texto(texto):
    texto = texto.lower().strip().replace(".", "").replace(",", "").replace(" ", "")
    return re.sub(r'[^\w\s]', '', texto.lower().strip())

def fin(inicio):
    segundos = time.time() - inicio
    dias = int(segundos // (24 * 3600))
    segundos = segundos % (24 * 3600)
    horas = int(segundos // 3600)
    segundos %= 3600
    minutos = int(segundos // 60)
    segundos = int(segundos % 60) 
    return f"{dias:02d}d {horas:02d}:{minutos:02d}:{segundos:02d}"

def pregunta_IA(texto):
    inicio = time.time()
    logg("Iniciando pregunta")
    # Llamar a endpoint para analizar intención
    payload = {
        "pregunta": texto,
        "cliente_id": CLIENTE_ID
    }
    # Reproduciendo wait
    agi.stream_file(f"custom/wait", "1234567890*#")
    r = requests.post(f"{LLM_ENDPOINT}/preguntar", json=payload)
    if not r.ok:
        respuesta = "Lo siento, no pude procesar su consulta."
    else:
        data = r.json()
        respuesta = data.get("respuesta", "No puedo responder en este momento")
        requiere_validacion = data.get("requiere_validacion", "No puedo responder en este momento")
        logg(f"Respuesta: ({requiere_validacion}) {respuesta} ")
    respuesta = respuesta.replace("RD$", "")
    logg("Fin pregunta. Tiempo: " + fin(inicio))
    return respuesta, requiere_validacion

def pedir_cedula():
    """Solicitar la cédula al asociado usando DTMF y validarla en Oracle."""
    intentos = 0
    max_intentos = 3

    while intentos < max_intentos:
        agi.stream_file("custom/pida_cedula")  # "Por favor marque su número de cédula seguido de numeral"
        cedula = agi.get_data('beep', 6000, 11)  # 6 segundos, máximo 11 dígitos
        cedula = cedula.strip()

        logg(f"Cédula capturada: {cedula}")

        if len(cedula) != 11 or not cedula.isdigit():
            logg("Cédula inválida en formato")
            agi.stream_file("custom/cedula_invalida")  # "Número inválido, por favor intente de nuevo"
            intentos += 1
            continue

        cliente_id = buscar_cliente_por_cedula(cedula)
        if cliente_id:
            logg(f"Cédula válida. Cliente encontrado: {cliente_id}")
            return cliente_id
        else:
            agi.stream_file("custom/cedula_no_encontrada")  # "No encontramos su número, intente de nuevo."
            intentos += 1

    # Si llega aquí, falló
    agi.stream_file("custom/muchas_reintentos")  # "Hemos recibido varios intentos fallidos, finalizando la llamada."
    agi.hangup()
    return None

def buscar_cliente_por_cedula(num_id):
    inicio = time.time()
    """Buscar cliente en Oracle por número de cédula."""
    try:
        payload = {
            "num_id": num_id
        }
        
        if num_id:
            r = requests.post(f"{LLM_ENDPOINT}/buscar", json=payload)          
            r.raise_for_status()
            cod_cliente = r.json()["cod_cliente"]
            fin_ = fin(inicio)
            logg(f"Resultado buscar tiempo {fin_}: '{cod_cliente}'")
        return cod_cliente        
    except Exception as e:
        logg(f"Error buscando cliente por cédula: {e}")
        return None



def pregunta_cliente():
    n = random.randint(1, 9999999999) # generate a random number between 1 and 9999999999
    filename = str(n).zfill(10) # pad with zeros and add extension
    wav_usr  = f"{savepath}/{filename}"          
    logg("Grabación del cliente...")
    agi.record_file(wav_usr, "wav", "#", 8000, 0, "", 2)
    logg(f"Procesando grabación: '{wav_usr}.wav'...")
    # Whisper
    result = model.transcribe(f"{wav_usr}.wav", language="es", temperature=0.0)
    texto = result["text"]
    logg(f"whisper entendio: '{texto}'")
    texto_clean = limpiar_texto(texto)
    logg(f"Texto limpiado: '{texto}'")
    if texto_clean in ["salir", "no", "eso es todo", "terminé", "finalizar", "fin", "gracias"]:
        return False
    if texto_clean:
        respuesta, requiere_validacion = pregunta_IA(texto)
        if requiere_validacion == "S":
            logg(f"Se requiere validación para intención: {intencion}")
            nuevo_cliente_id = pedir_cedula()
            if not nuevo_cliente_id:
                agi.stream_file("custom/colgando")  # "No pudimos validar su identidad. Finalizando."
                agi.hangup()
                return False
            else:
                global CLIENTE_ID
                CLIENTE_ID = nuevo_cliente_id
                logg(f"Cliente validado: {CLIENTE_ID}")
        tts(respuesta, filename)
        # Reproduciendo askagain
        agi.stream_file(f"custom/askagain", "1234567890*#")
    else:
        agi.stream_file("custom/repeat", "1234567890*#")
    return True

def aiff_to_wav(aiff_path, wav_path):
    logg(f"convirtiendo {aiff_path}...", 1)
    if not os.path.exists(aiff_path):
        logg(f"AIFF No existe el archivo AIFF: {aiff_path}", 1)        
        raise FileNotFoundError(f"No existe el archivo AIFF: {aiff_path}")
    logg(f"AIFF archivo '{aiff_path}' existe OK...", 1)
    #ffmpeg -hide_banner -loglevel error -i /opt/agi/app/sound/10030011900039_response.aiff -ar 8000 /opt/agi/app/sound/10030011900039_response.wav
    try:
        cmd = [
            'ffmpeg',
            '-y',
            '-hide_banner',
            #'-loglevel', 'error',            
            '-i', aiff_path,
            '-ar', '8000',
            #'-af', '"equalizer=f=440:width_type=o:width=2:g=2,equalizer=f=1000:width_type=h:width=200:g=-8"',
            wav_path
        ]
        texto = " ".join(cmd)
        logg(f"Ejecutando ffmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.stderr:
            stder = result.stderr.strip()
            logg(f"FFmpeg STDERR: {stder}")

        if result.returncode != 0:
            logg(f"Error ejecutando ffmpeg {result.stderr}")
            raise RuntimeError(f"FFmpeg falló:\n{result.stderr}")

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            logg("Archivo WAV no generado o está vacío", 2)
            raise RuntimeError("FFmpeg no generó salida válida")

        logg(f"Archivo WAV generado correctamente: {wav_path}")
        os.remove(f"{aiff_path}")
    except subprocess.CalledProcessError as e:
        logg(f"AIFF Error ejecutando ffmpeg: {e}", 1)
        raise RuntimeError(f"AIFF Error ejecutando ffmpeg: {e}")

def tts(text, filename):
    usr_resp = f"{filename}_response"
    usr_wav = f"custom/{usr_resp}"
    wav_resp = f"{savepath}/{usr_resp}"
    wav_path = f"{wav_resp}.wav"
    aiff_path = f"{wav_resp}.aiff"
    logg("generando audio con TTS...")    
   # Convertir respuesta a audio
    tts_payload = {
        "text": text,
        "filename": filename,
        "voice": VOICE_NAME
    }

    tts_resp = requests.post(TTS_SERVER, headers=headers, json=tts_payload)
    if tts_resp.ok:
        with open(aiff_path, "wb") as f:
            f.write(tts_resp.content)
        aiff_to_wav(aiff_path, wav_path)
        logg(f"Reproduciendo respuesta {usr_wav}")
        agi.stream_file(f"{usr_wav}")
        
        #os.remove(f"{wav_path}")
    else:
        logg("Error generando respuesta TTS")


# Start program
try:
  model = whisper.load_model("medium")
  agi = AGI()
  agi.answer()  
  callerId = agi.env['agi_callerid']
  logg(f"Llamada entrante desde {callerId}")
  logg("Reproducir Bienvenida!")
  # Play welcome
  agi.stream_file(f"custom/welcome", "1234567890*#")
  agi.stream_file(f"custom/ask", "1234567890*#")
  # Inicio ciclo preguntas y respuestas
  while pregunta_cliente():
    logg("Procesando")
    
  # Fin ciclo preguntas y respuestas
  logg(f"Colgando! Bye!")
  agi.stream_file("custom/thankyou")  # Audio de despedida  
  agi.hangup()
except Exception as e:
  logg(f"Error: {e}", 1)
  logg(f"Colgando! Bye!")
  agi.stream_file("custom/thankyou")  # Audio de despedida
  agi.hangup()
  raise
