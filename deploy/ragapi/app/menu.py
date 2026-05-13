"""Menú interactivo para WhatsApp / Zenvia.

El árbol del menú se define en `menus.json`. Cada `row.id` lleva un prefijo
que indica qué hacer cuando el usuario lo elige:

    MENU:<id>            -> navegar al menú con ese id
    INFO:<clave>         -> enviar el texto fijo definido en menus.json["info"][clave]
    LLM:<intent>|<query> -> llamar al flujo LLM con el intent y la pregunta dados
    OTP:<intent>|<query> -> arrancar la validación con OTP (cédula -> OTP) y, una
                            vez validado, ejecutar el LLM con ese intent/pregunta
    ACTION:<accion>      -> acciones internas (p.ej. `libre` desactiva el menú)
"""

import json
import os
from typing import Optional, Tuple

MENUS_PATH = os.path.join(os.path.dirname(__file__), "menus.json")
_menus_cache = None
_menus_mtime = 0.0


def cargar_menus() -> dict:
    """Carga menus.json y lo recarga automáticamente si el archivo cambió."""
    global _menus_cache, _menus_mtime
    try:
        mtime = os.path.getmtime(MENUS_PATH)
    except OSError:
        mtime = 0.0
    if _menus_cache is None or mtime != _menus_mtime:
        with open(MENUS_PATH, "r", encoding="utf-8") as f:
            _menus_cache = json.load(f)
        _menus_mtime = mtime
    return _menus_cache


def recargar_menus() -> dict:
    global _menus_cache, _menus_mtime
    _menus_cache = None
    _menus_mtime = 0.0
    return cargar_menus()


def get_menu(menu_id: str) -> Optional[dict]:
    return cargar_menus().get(menu_id)


def get_info(info_id: str) -> Optional[str]:
    return cargar_menus().get("info", {}).get(info_id)


def armar_contenido_list(menu_id: str) -> Optional[dict]:
    """Devuelve el bloque `contents[0]` (type=list) para Zenvia, o None.

    Zenvia v2: header/body/footer como strings, button y sections planos.
    """
    menu = get_menu(menu_id)
    if not menu:
        return None

    contenido = {
        "type": "list",
        "header":   (menu.get("header") or "")[:60],
        "body":     (menu.get("body") or "")[:1024],
        "button":   (menu.get("button") or "Ver opciones")[:20],
        "sections": menu.get("sections", []),
    }
    footer = menu.get("footer")
    if footer:
        contenido["footer"] = footer[:60]
    return contenido


def resolver_payload(payload_id: str) -> Tuple[str, str]:
    """Parsea el id devuelto por una row. Devuelve (tipo, valor).

    tipo ∈ {"MENU","INFO","LLM","OTP","ACTION",""}.
    Para LLM y OTP, `valor` es "intent|query"; usar `split_intent_query`.
    """
    if not payload_id or ":" not in payload_id:
        return ("", "")
    tipo, _, valor = payload_id.partition(":")
    return (tipo.strip().upper(), valor.strip())


def split_intent_query(valor: str) -> Tuple[str, str]:
    """Para payloads INTENT/OTP: separa 'intent|query'."""
    if "|" in valor:
        intent, _, query = valor.partition("|")
        return (intent.strip(), query.strip())
    return (valor.strip(), "")


_INTROS_MARKETING = {
    ('producto','cuenta'):         ("Te presentamos esta cuenta:", "Te presentamos nuestras cuentas:"),
    ('producto','prestamo'):       ("Conoce este tipo de préstamo:", "Nuestros préstamos te apoyan en cada etapa:"),
    ('producto','prestamo_feria'): ("Conoce este financiamiento de la Expo Feria Madre Feliz:", "Nuestros financiamientos especiales de la Expo Feria Madre Feliz:"),
    ('producto','certificado'):    ("Conoce nuestro Certificado Financiero:", "Conoce nuestros Certificados Financieros:"),
    ('producto','tarifa'):         ("Estas son nuestras tarifas vigentes:", "Estas son nuestras tarifas vigentes:"),
    ('producto','membresia'):      ("Conoce este tipo de membresía:", "Tenemos estos tipos de membresía:"),
    ('producto','solicitud'):      ("Así puedes solicitarlo:", "Así puedes solicitarlo:"),
    ('producto','requisito'):      ("Estos son los requisitos:", "Estos son los requisitos:"),
    ('producto','proceso'):        ("Estos son los pasos:", "Estos son los pasos:"),
    ('servicio','salud'):          ("Te ofrecemos este servicio de salud:", "Nuestros servicios de salud para ti:"),
    ('servicio','recreacion'):     ("Disfruta de este beneficio recreativo:", "Disfruta de nuestros beneficios recreativos:"),
    ('servicio','social'):         ("Conoce este programa social:", "Nuestros programas sociales:"),
    ('empresa','identidad'):       ("Sobre nosotros:", "Sobre nosotros:"),
    ('empresa','historia'):        ("Nuestra historia:", "Nuestra historia:"),
    ('empresa','filosofia'):       ("Nuestra filosofía:", "Nuestra filosofía:"),
    ('empresa','asociado'):        ("Información para asociados:", "Información para asociados:"),
    ('empresa','contacto'):        ("Estamos para servirte:", "Estamos para servirte. Nuestros canales:"),
    ('empresa','estructura'):      ("Sobre nuestra organización:", "Sobre nuestra organización:"),
    ('empresa','politica'):        ("Nuestro compromiso institucional:", "Nuestros compromisos institucionales:"),
    ('sucursal','direccion'):      ("Esta es nuestra oficina:", "Estas son nuestras oficinas:"),
}

def _intro_marketing(contexto):
    """Devuelve un encabezado en tono profesional/marketing basado en tipo/subtipo
    del primer item del contexto. Usa singular si hay 1 item, plural si hay varios."""
    if not isinstance(contexto, list) or not contexto:
        return None
    primero = next((c for c in contexto if isinstance(c, dict)), None)
    if not primero:
        return None
    par = (primero.get('tipo'), primero.get('subtipo'))
    intros = _INTROS_MARKETING.get(par)
    if not intros:
        return None
    return intros[0] if len(contexto) == 1 else intros[1]


def formatear_contexto_general(contexto, limite: int = 8) -> Optional[str]:
    """Renderiza una lista de entradas de context_cvr.jsonl como texto WhatsApp.

    Devuelve None si no hay contexto utilizable.
    """
    if not contexto:
        return None
    if isinstance(contexto, str):
        return contexto.strip() or None
    if not isinstance(contexto, list):
        return None

    partes = []
    for c in contexto[:limite]:
        if not isinstance(c, dict):
            continue
        nombre = c.get("nombre") or (c.get("subtipo") or "").replace("_", " ").title()
        contenido = (c.get("contenido") or "").strip()
        descripcion = (c.get("descripcion") or "").strip()

        extras = []
        if c.get("fecha_inicio"):
            extras.append(f"desde el {c['fecha_inicio']}")
        if c.get("fecha_fin"):
            extras.append(f"hasta el {c['fecha_fin']}")
        if c.get("horario"):
            h = c["horario"]
            if isinstance(h, list):
                h = "; ".join(h)
            extras.append(f"horario: {h}")
        if c.get("direccion"):
            extras.append(f"📍 {c['direccion']}")
        if c.get("telefonos"):
            tel = c["telefonos"]
            if isinstance(tel, list):
                tel = ", ".join(tel)
            extras.append(f"☎ {tel}")
        sitio = c.get("sitio_web")

        bloque = ""
        if nombre:
            bloque += f"*{nombre}*\n"
        if descripcion:
            bloque += descripcion + "\n"
        if contenido:
            bloque += contenido + "\n"
        if extras:
            bloque += " · ".join(extras) + "\n"
        if sitio:
            bloque += f"🌐 {sitio}\n"
        bloque = bloque.rstrip()
        if bloque:
            partes.append(bloque)

    if not partes:
        return None
    cuerpo = "\n\n".join(partes)
    intro = _intro_marketing(contexto)
    return f"{intro}\n\n{cuerpo}" if intro else cuerpo


def formatear_contexto_personal(contexto) -> str:
    """Renderiza los productos del cliente agrupados por categoría
    (Préstamos, Certificados, Cuentas, Artículos de Feria) con saludo personalizado."""
    import json as _json

    sin_datos = "No encontramos productos activos asociados a tu cuenta. Si crees que es un error, comunícate con la cooperativa."

    if not contexto:
        return sin_datos
    productos = contexto
    if isinstance(productos, str):
        try:
            productos = _json.loads(productos)
        except Exception:
            return productos
    if isinstance(productos, dict):
        productos = [productos]
    if not isinstance(productos, list) or not productos:
        return sin_datos

    grupos = {"prestamo": [], "certificado": [], "cuenta": [], "feria": []}
    nombre_asociado = None
    for p in productos:
        if not isinstance(p, dict):
            continue
        if not nombre_asociado:
            nombre_asociado = p.get("nombre_asociado")
        subtipo = (p.get("subtipo") or "").lower()
        tipo = (p.get("tipo") or "").lower()
        if subtipo == "prestamo_feria" or tipo == "articulo":
            grupos["feria"].append(p)
        elif subtipo in ("prestamo", "credito"):
            grupos["prestamo"].append(p)
        elif subtipo == "certificado":
            grupos["certificado"].append(p)
        elif subtipo == "cuenta":
            grupos["cuenta"].append(p)
        else:
            grupos["cuenta"].append(p)

    if not any(grupos.values()):
        return sin_datos

    primer_nombre = (nombre_asociado or "").strip().split(" ")[0]
    if primer_nombre:
        saludo = f"¡Hola {primer_nombre}! Este es el resumen de tus productos en Vega Real:"
    else:
        saludo = "Este es el resumen de tus productos en Vega Real:"

    def _linea_producto(p):
        nombre = p.get("descripcion") or "Producto"
        balance = p.get("saldo_formateado", "")
        if balance:
            return f"• {nombre} — Balance: {balance}"
        return f"• {nombre}"

    def _linea_feria(p):
        nombre = p.get("descripcion_articulo") or "Artículo de feria"
        estado = (p.get("estado_articulo") or "").strip()
        if estado:
            return f"• {nombre} — Estado: {estado}"
        return f"• {nombre}"

    bloques = [saludo]
    secciones = [
        ("*Préstamos*",          grupos["prestamo"],    _linea_producto),
        ("*Certificados*",       grupos["certificado"], _linea_producto),
        ("*Cuentas*",            grupos["cuenta"],      _linea_producto),
        ("*Artículos de Feria*", grupos["feria"],       _linea_feria),
    ]
    for header, items, formatter in secciones:
        if not items:
            continue
        lineas = [header] + [formatter(p) for p in items]
        bloques.append("\n".join(lineas))

    return "\n\n".join(bloques)
