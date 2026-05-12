import json
import requests
import time
import re
from typing import Dict, List, Optional, Union
from rag_db import logg
from datetime import datetime, timedelta
#from zoneinfo import ZoneInfo

data = entities = synonyms = None 

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

def obtener_fecha_desde_texto(texto: str) -> str:
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
    conocimiento = load_jsonl_from_file('/app/context_cvr.jsonl')
    for item in conocimiento:
        for entity in entities:
            if entity["tipo"] == item["tipo"]:
                if entity["subtipo"] == item["subtipo"]:
                    if entity["valor"]:
                        if entity["valor"] == item["valor"]:
                            retorno.append(item)
                    else:
                        retorno.append(item)
    return retorno


def conocimiento_general_old(parte=None):
    conocimiento = ""
    try:
        with open('/app/contexto_cvr.json', 'r', encoding='utf-8') as json_file:
            conocimiento = json_file.read()
            if parte:
                JSON = json.loads(conocimiento)
                conocimiento = JSON[parte]
    except IOError:
        logg("File 'contexto_cvr.json' not accessible, ignoring...")
    
    return conocimiento

def construir_prompt(intencion, pregunta, contexto, conocimiento_extra=" "):
    plantilla = ""
    ahora = "[FECHA_ACTUAL]: " + datetime.now().isoformat()+"-04:00 \n\n"
    intencion = intencion.lower()
    try:
        with open('/app/plantillas.json', 'r', encoding='utf-8') as json_file:
            plantillas = json_file.read()
            if intencion:
                JSON = json.loads(plantillas)
                plantilla = JSON[intencion]
    except IOError:
        logg("File 'plantillas.json' not accessible, ignoring...")

    
    if not plantilla:
        plantilla = JSON["default"] 
    
    if plantilla:
        logg(f"Usando Plantilla: [{intencion}] " )

    plantilla = ahora + plantilla
    
    return plantilla.format(
        contexto=contexto,
        conocimiento=conocimiento_extra,
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
        
        return False, True, intent, None
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

def process_query(query: str) -> str:
        """Procesa una consulta del usuario y devuelve una respuesta"""
        logg(f"process_query: query = '{query}'")
        intent = detect_intent(query)
        result = {
                "intent": None,
                "type": "general",
                "entity": None,
                "context": None
            }
        result["intent"] = intent        
        
        posesivos = ["mi ", "mis ", "de mi", "de mis"]
        if any(p in query for p in posesivos):
            intent = "saldo"
            result["type"] = "personal"
            result["intent"] = intent
        tipo = result["type"]
        local_entities = extract_entities(intent, query)
        result["entity"] = local_entities
        logg(f"process_query: intent type '{tipo}' intent = '{intent}' entities = '{local_entities}'")
        if result["type"] == "general":
            logg(f"process_query: buscando entidades generales '{intent}'")
            result["context"] = conocimiento_general(local_entities)
            return result
        else: #Personales que requieren validacion OTP
            logg(f"process_query: buscando entidades personales '{intent}'")
            result["context"] = ""
            return result
                      
        #

def normalize_text(text: str) -> str:
    """Normaliza texto para comparación"""
    text = text.lower().strip()
    replacements = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ü': 'u', 'ñ': 'n'
        }
    synonyms = load_json_from_file('/app/synonyms.json')
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    # Reemplazar sinónimos
    for syn, main in synonyms.items():
        text = text.replace(syn, main)
    return text

def load_json_from_file(filepath) -> dict:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except IOError:
        logg(f"File '{filepath}' not accessible, ignoring...")
        return None
    
def load_jsonl_from_file(filepath) -> dict:
    JSONL = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for linea in f:
                if not linea.strip().startswith("#") and linea.strip():
                    obj = json.loads(linea)
                    JSONL.append(obj)
        return JSONL
    except IOError:
        logg(f"File '{filepath}' not accessible, ignoring...")
        return None

def detect_intent(query: str) -> str:
    """Detecta la intención principal del usuario"""
    query = normalize_text(query)
    logg(f"detect_intent('{query}')")
    intents = load_json_from_file("/app/intents.json")

    for intent, keywords in intents.items():
        if any(keyword in query for keyword in keywords):
            return intent
    
    query = query.replace('-','')
    if query.isdigit() and len(query) in [10, 11]:
        return 'cedula'
    
    return 'general'

def extract_entities(intent, query: str) -> Dict:
    query = normalize_text(query)
    logg(f"extract_entities('{query}')")
    found = []
    local_entities = load_jsonl_from_file('/app/index_semantico_entidades.jsonl')
    for item in local_entities:
        if intent == item["tipo"]:
            #logg(f"extract_entities: item: {item} in '{query}'")
            for campo in ['tipo', 'subtipo', 'valor', 'nombre', 'descripcion', 'contenido', 'municipio', 'provincia', 'pais', 'telefonos', 'extensiones']:
                if campo in item:
                    campo_arr = str(item[campo]).lower().split("_")
                    for c in campo_arr:
                        #logg(f"extract_entities: campo: {campo} = '{c}'  in '{query}'")
                        if c in query:
                            found.append(item)
                            logg(f"extract_entities: found: {found} -> '{c}' in '{query}'")
    # Fallback: si no se encontró nada, intentar buscar por municipio/provincia/valor/nombre
    if not found:
        tokens = set(query.split())
        for item in (local_entities or []):
            try:
                if item.get('tipo') != intent:
                    continue
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

def extract_entities2(query: str) -> Dict:
    """Extrae entidades relevantes de la consulta"""
    query = normalize_text(query)
    logg(f"extract_entities('{query}')")
    loc_entities = {}
    entities = load_json_from_file('/app/entities.json') 

    
    # Buscar en todas las categorías de entidades
    for entity_type, values in entities.items():
        found = []
        for value in values:            
            norm_value = normalize_text(value)
            #logg(f"extract_entities: '{entity_type}.{norm_value}' in '{query}'")
            # Buscar coincidencias exactas o parciales
            if norm_value in query or any(part in query for part in norm_value.split('_')):
                found.append(value)
                logg(f"extract_entities: found: {found} -> '{norm_value}' in '{query}'")
        
        if found:
            loc_entities[entity_type] = found
            
    # Detección especial para municipios/provincias
    location_entities = []
    
    for loc in entities['municipio'] + entities['provincia']:
        if normalize_text(loc) in query:
            location_entities.append(loc)
    
    if location_entities:
        loc_entities['ubicacion'] = location_entities

    #print(loc_entities)    
    return loc_entities

def preguntar_llm(intencion, pregunta, contexto, conocimiento_extra, max_reintentos=2, modelo="mistral:7b-instruct", endpoint="http://localhost:11434/api/generate"):
    """
    Envía la pregunta a Mistral (u otro modelo), valida la respuesta como JSON,
    reintenta si es necesario, y maneja error amigablemente.
    """

    prompt = construir_prompt(intencion, pregunta, contexto, conocimiento_extra)
    logg(f"preguntar_llm: '{intencion}' -> {pregunta}")
    #logg(f"\r\n=======INICIO CONTEXTO============\r\n{contexto}\r\n=========FIN CONTEXTO==========")
    logg(f"preguntar_llm:\r\n=======INICIO PROMPT============\r\n{prompt}\r\n=========FIN PROMPT==========")
    logg("preguntar_llm: Analizando respuesta...")
    for intento in range(max_reintentos + 1):
        try:
            response = requests.post(endpoint, json={
                "model": modelo,
                "prompt": prompt,
                "stream": False
            }, timeout=120)

            if response.status_code != 200:
                logg(f"preguntar_llm: Error en conexión (código {response.status_code})")
                continue

            respuesta_llm = response.json().get("response", "")
            respuesta_llm = respuesta_llm.replace("[RESPUESTA]:", "")
            if respuesta_llm:
                logg(f"preguntar_llm: '{intencion}' \r\nUsuario: {pregunta} \r\nAsistente:{respuesta_llm}")
                return respuesta_llm  # JSON correcto
            else:
                logg(f"preguntar_llm: Intento {intento + 1}: Respuesta inválida, reintentando...")
                time.sleep(0.5)

        except Exception as e:
            logg(f"preguntar_llm: Error durante consulta a LLM: {e}")
            continue

    # Si no se pudo validar en todos los intentos:
    return "Estamos presentando inconvenientes, por favor intenta en unos minutos"
