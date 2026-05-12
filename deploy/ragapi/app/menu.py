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
    return "\n\n".join(partes)


def formatear_contexto_personal(contexto) -> str:
    """Renderiza los productos del cliente (cuentas, créditos, artículos de feria)."""
    import json as _json

    if not contexto:
        return "No encontramos información asociada a tu cuenta."

    productos = contexto
    if isinstance(productos, str):
        try:
            productos = _json.loads(productos)
        except Exception:
            return productos
    if isinstance(productos, dict):
        productos = [productos]
    if not isinstance(productos, list) or not productos:
        return "No encontramos información asociada a tu cuenta."

    partes = []
    for p in productos:
        if not isinstance(p, dict):
            continue
        subtipo = p.get("subtipo", "")
        balance = p.get("saldo_formateado", "")

        if subtipo == "prestamo_feria" or p.get("tipo") == "articulo":
            nombre = p.get("descripcion_articulo") or "Artículo de feria"
            estado = p.get("estado_articulo", "")
            bloque = f"*{nombre}*"
            if estado:
                bloque += f"\nEstado: {estado}"
            partes.append(bloque)
        elif subtipo in ("cuenta", "credito", "prestamo"):
            nombre = p.get("descripcion") or subtipo.title()
            bloque = f"*{nombre}*"
            if balance:
                bloque += f"\nBalance: {balance}"
            partes.append(bloque)
        else:
            nombre = p.get("nombre") or p.get("descripcion") or subtipo or "Producto"
            bloque = f"*{nombre}*"
            if balance:
                bloque += f"\nBalance: {balance}"
            partes.append(bloque)

    if not partes:
        return "No encontramos información asociada a tu cuenta."
    return "\n\n".join(partes)
