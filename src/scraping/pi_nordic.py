"""Extracción del JSON de __NORDIC_RENDERING_CTX__ (sitios de Mercado Libre).

Portal Inmobiliario (sitio de Mercado Libre) sirve sus páginas
server-rendered con todo el estado de la aplicación dentro de un script:

    <script id="__NORDIC_RENDERING_CTX__">_n.ctx.r={...JSON...};
    _n.ctx.r.assets.manifest=new Map([...]);...</script>

Solo la primera asignación (`_n.ctx.r=`) es JSON parseable; lo que sigue
son statements de JavaScript. Este módulo aísla y parsea ese objeto.

Funciones puras: reciben HTML como string y devuelven dicts, sin tocar
red ni disco.
"""

from __future__ import annotations

import json
from typing import Any

ID_SCRIPT = "__NORDIC_RENDERING_CTX__"
PREFIJO_JSON = "_n.ctx.r="


def extraer_nordic(html: str) -> dict[str, Any]:
    """Devuelve el dict `_n.ctx.r` de la página, o {} si no existe.

    Usa JSONDecoder.raw_decode para parsear solo el primer objeto JSON del
    script, ignorando los statements JS que vienen después.
    """
    marcador = f'id="{ID_SCRIPT}"'
    inicio_script = html.find(marcador)
    if inicio_script == -1:
        return {}
    inicio_json = html.find(PREFIJO_JSON, inicio_script)
    if inicio_json == -1:
        return {}
    try:
        datos, _ = json.JSONDecoder().raw_decode(html, inicio_json + len(PREFIJO_JSON))
    except json.JSONDecodeError:
        return {}
    return datos if isinstance(datos, dict) else {}


def extraer_estado_inicial(html: str) -> dict[str, Any]:
    """Devuelve `appProps.pageProps.initialState` de la página, o {}.

    El estado de búsqueda (results, pagination, melidata_track) y el de la
    página de detalle (components, breadcrumb, schema) viven aquí.
    """
    app_props = extraer_nordic(html).get("appProps")
    if not isinstance(app_props, dict):
        return {}
    page_props = app_props.get("pageProps")
    if not isinstance(page_props, dict):
        return {}
    estado = page_props.get("initialState")
    return estado if isinstance(estado, dict) else {}
