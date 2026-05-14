#!/opt/rag/bin/python
"""
test_process_query.py
---------------------
Script para probar process_query() y las funciones relacionadas
(detect_intent, extract_entities, conocimiento_general) de api_llm.py
sin necesidad de levantar Flask ni conectar a la base de datos.

Uso:
    python test_process_query.py
    python test_process_query.py "sucursal en La Vega"
    python test_process_query.py --list        # lista los casos predefinidos
    python test_process_query.py --caso 3      # ejecuta sólo el caso 3
"""

import sys
import os
import json
import re
import argparse
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configurar variables de entorno antes de importar api_llm
# ---------------------------------------------------------------------------
os.environ.setdefault("OLLAMA_URL",       "http://ollama:11434")
os.environ.setdefault("OLLAMA_MODEL",     "realia-cvr")
os.environ.setdefault("OLLAMA_HOST",      "0.0.0.0")
os.environ.setdefault("OPENAI_BASE_URL",  "http://ollama:11434")
os.environ.setdefault("OPENAI_API_KEY",   "test-key")
os.environ.setdefault("BASE_PATH",        "/opt/rag/app")
os.environ.setdefault("USE_LLM",          "false")
os.environ.setdefault("REDIS_DBSERVER",   "redis")
os.environ.setdefault("REDIS_DBPASSWORD", "sOmE_sEcUrE_pAsS")
os.environ.setdefault("VAPID_PUBLIC_KEY", "test")
os.environ.setdefault("VAPID_PRIVATE_KEY","test")
os.environ.setdefault("VAPID_CLAIMS",     "test@test.com")
os.environ.setdefault("ZENVIA_API",       "http://localhost")
os.environ.setdefault("ZENVIA_TOKEN",     "test")
os.environ.setdefault("ZENVIA_WANUMBER",  "18001234567")
os.environ.setdefault("ENCUESTA_URL",     "http://localhost")
os.environ.setdefault("ENCUESTA_API_KEY", "test")
os.environ.setdefault("ENCUESTA_ID",      "0")

# Cambiar al directorio de la app para que los JSONL se encuentren por ruta relativa
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# ---------------------------------------------------------------------------
# Importar las funciones que queremos probar directamente desde api_llm
# ---------------------------------------------------------------------------
try:
    from api_llm import (
        process_query,
        detect_intent,
        extract_entities,
        conocimiento_general,
        normalize_text,
    )
    import menu as menu_mod
except ImportError as e:
    print(f"[ERROR] No se pudo importar api_llm: {e}")
    print("Asegúrate de ejecutar este script dentro del contenedor realia-ragapi-1:")
    print("  docker exec -it realia-ragapi-1 python /opt/rag/app/test_process_query.py")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Casos de prueba predefinidos
# ---------------------------------------------------------------------------
CASOS = [
    # (descripción, query)
    ( 1, "Saludo simple",                    "hola, buenos días"),
    ( 2, "Cierre",                           "gracias, hasta luego"),
    ( 3, "Sucursal La Vega",                 "sucursal provincia La Vega"),
    ( 4, "Sucursal Cotuí",                   "sucursal Sánchez Ramírez"),
    ( 5, "Sucursal Espaillat",               "sucursal Espaillat"),
    ( 6, "Sucursal New York",                "sucursal New York"),
    ( 7, "Cuenta aportaciones",              "cuenta aportaciones"),
    ( 8, "Cuenta ahorro retirable",          "cuenta ahorro retirable"),
    ( 9, "Préstamo hipotecario",             "préstamo hipotecario"),
    (10, "Préstamo consumo",                 "préstamo consumo"),
    (11, "Préstamo feria paneles solares",   "producto/prestamo_feria/paneles_solares"),
    (12, "Certificado financiero",           "certificado financiero"),
    (13, "Misión cooperativa",               "misión de la cooperativa"),
    (14, "Cómo afiliarme",                   "cómo me puedo afiliar"),
    (15, "Plan farmacia",                    "servicio plan farmacia"),
    (16, "Casa club recreación",             "casa club recreación"),
    (17, "Horarios de la central",           "horario sucursal central"),
    (18, "Teléfono cooperativa",             "teléfono de la cooperativa"),
    (19, "Tarjeta de débito",                "tarjeta débito real"),
    (20, "Consulta ambigua (general)",       "necesito información"),
]

# ---------------------------------------------------------------------------
# Utilidades de presentación
# ---------------------------------------------------------------------------
BOLD  = "\033[1m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"

def separador(texto="", ancho=70):
    if texto:
        lado = (ancho - len(texto) - 2) // 2
        print(f"{CYAN}{'─'*lado} {texto} {'─'*lado}{RESET}")
    else:
        print(f"{CYAN}{'─'*ancho}{RESET}")

def imprimir_resultado(num, desc, query, result):
    separador(f"Caso {num}: {desc}")
    print(f"  {BOLD}Query:{RESET}         {query!r}")
    print(f"  {BOLD}Intent:{RESET}        {YELLOW}{result.get('intent')}{RESET}  "
          f"(fuente: {result.get('intent_source')})")
    print(f"  {BOLD}Tipo:{RESET}          {result.get('type')}")

    entities = result.get("entity") or []
    if entities:
        print(f"  {BOLD}Entidades:{RESET}")
        for e in entities:
            tipo    = e.get("tipo","")
            subtipo = e.get("subtipo","")
            valor   = e.get("valor","")
            print(f"    • {tipo}/{subtipo}/{valor}")
    else:
        print(f"  {BOLD}Entidades:{RESET}     {RED}(ninguna){RESET}")

    contexto = result.get("context") or []
    if contexto:
        print(f"  {BOLD}Contexto ({len(contexto)} ítem(s)):{RESET}")
        for i, c in enumerate(contexto, 1):
            nombre   = c.get("nombre") or c.get("valor") or c.get("contenido","")
            contenido= c.get("contenido","")
            linea    = f"{nombre}: {contenido}" if nombre != contenido else nombre
            # Truncar líneas largas
            if len(linea) > 120:
                linea = linea[:117] + "..."
            print(f"    [{i}] {GREEN}{linea}{RESET}")
    else:
        print(f"  {BOLD}Contexto:{RESET}      {RED}(vacío){RESET}")

def ejecutar_caso(num, desc, query):
    try:
        result = process_query(query)
        imprimir_resultado(num, desc, query, result)
    except Exception as e:
        separador(f"Caso {num}: {desc}")
        print(f"  {RED}ERROR: {e}{RESET}")
        import traceback; traceback.print_exc()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Prueba process_query() de api_llm.py"
    )
    parser.add_argument("query", nargs="?",
                        help="Query libre a probar directamente")
    parser.add_argument("--list", action="store_true",
                        help="Lista los casos de prueba predefinidos")
    parser.add_argument("--caso", type=int, metavar="N",
                        help="Ejecuta sólo el caso número N")
    args = parser.parse_args()

    print()
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  TEST: process_query()  —  {SCRIPT_DIR}{RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"  USE_LLM    : {os.getenv('USE_LLM')}")
    print(f"  OLLAMA_URL : {os.getenv('OLLAMA_URL')}")
    print(f"  MODEL      : {os.getenv('OLLAMA_MODEL')}")
    print()

    if args.list:
        print(f"  {'#':>3}  {'Descripción':<35}  Query")
        print(f"  {'─'*3}  {'─'*35}  {'─'*30}")
        for num, desc, q in CASOS:
            print(f"  {num:>3}  {desc:<35}  {q!r}")
        print()
        return

    if args.query:
        # Query libre pasado como argumento
        ejecutar_caso(0, "Query libre", args.query)
    elif args.caso:
        caso = next(((n,d,q) for n,d,q in CASOS if n == args.caso), None)
        if caso:
            ejecutar_caso(*caso)
        else:
            print(f"{RED}Caso {args.caso} no encontrado. Usa --list para ver los disponibles.{RESET}")
            sys.exit(1)
    else:
        # Ejecutar todos los casos
        for num, desc, query in CASOS:
            ejecutar_caso(num, desc, query)
        print()
        separador("FIN")
        print()

if __name__ == "__main__":
    main()
