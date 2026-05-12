from rag_db import logg
import json

def conocimiento_general(parte=None):
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

def construir_prompt(intencion, pregunta, contexto, conocimiento_extra=""):
    plantilla = ""
    intencion = intencion.lower()
    try:
        with open('/app/plantillas.json', 'r', encoding='utf-8') as json_file:
            plantillas = json_file.read()
            if intencion:
                JSON = json.loads(plantillas)
                plantilla = JSON[intencion]
    except IOError:
        logg("File 'plantillas.json' not accessible, ignoring...")
    
    encabezado = f"Intención detectada: {intencion.title()}\n\n"
    if plantilla:
        logg(f"Usando Plantilla: [{intencion}] " )
    if not plantilla:
        return encabezado + f"""Contexto:
            {contexto}

            Pregunta del asociado:
            {pregunta}

            Reglas:
            Responde con claridad. Si no sabes, responde "No tengo la información". Usa solo la información del contexto."""
    
    return plantilla.format(
        contexto=contexto,
        conocimiento=conocimiento_extra,
        pregunta=pregunta
    )