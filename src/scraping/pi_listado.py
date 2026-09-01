"""Parsing de páginas de listado de Portal Inmobiliario.

A diferencia de Yapo (HTML + selectores CSS), Portal Inmobiliario (sitio
de Mercado Libre) sirve todo el estado de la búsqueda como JSON dentro del
script `__NORDIC_RENDERING_CTX__`: este módulo parsea ese JSON en vez del
DOM, que es más frágil ante cambios de clases.

Funciones puras: reciben HTML como string y devuelven dicts, sin tocar
red ni disco.

Estructura (verificada contra el HTML real el 2026-08-19):
- `initialState.results`: los avisos son elementos {id: "POLYCARD",
  polycard: {...}}; el resto son intervenciones (filtros del sidebar, ads)
  que se ignoran.
- El estado viene triplicado dentro del script; la copia canónica es la
  de `initialState` (las otras viven en `appProps.sharedState.*`).
- `pagination.next_page.url`: URL de la siguiente página de resultados.
- `melidata_track.event_data.total`: total de avisos de la búsqueda.

Trampas conocidas:
- Los listados genéricos (ej. /venta/casa) mezclan proyectos inmobiliarios
  destacados; las rutas `propiedades-usadas` listan solo avisos
  individuales. Además se filtra por domain_id como defensa.
- `metadata.url` viene sin esquema ("portalinmobiliario.com/...").
- La moneda UF llega como "CLF" (ISO 4217) y se normaliza a "UF".
- `location.text` es texto sucio (direcciones, texto promocional, "0");
  la comuna es el último segmento separado por coma.
- Los m² vienen en formato es-CL ("5.000 m² totales", "163 m² útiles").
"""

from __future__ import annotations

from typing import Any

from src.scraping.numeros import (
    MONEDAS,
    a_entero,
    a_flotante,
    formatear_precio,
    parsear_m2,
)
from src.scraping.pi_nordic import extraer_estado_inicial

BASE_URL = "https://www.portalinmobiliario.com"

# Slug de categoría -> (ruta del listado, tipo_operacion, tipo_propiedad).
# Las rutas "propiedades-usadas" listan solo avisos individuales: los
# listados genéricos vienen poblados de proyectos inmobiliarios
# destacados (MLC-DEVELOPMENT_*, precio "Desde", specs en rangos).
CATEGORIAS_PRINCIPALES: dict[str, tuple[str, str, str]] = {
    "venta-casa": ("venta/casa/propiedades-usadas", "venta", "casa"),
    "venta-departamento": (
        "venta/departamento/propiedades-usadas",
        "venta",
        "departamento",
    ),
    "arriendo-casa": ("arriendo/casa/propiedades-usadas", "arriendo", "casa"),
    "arriendo-departamento": (
        "arriendo/departamento/propiedades-usadas",
        "arriendo",
        "departamento",
    ),
}

# Dominios de avisos individuales; los proyectos (MLC-DEVELOPMENT_*) y los
# ads se excluyen del parseo.
DOMINIOS_INDIVIDUALES = (
    "MLC-INDIVIDUAL_",
    "MLC-HOUSES_FOR_RENT",
    "MLC-APARTMENTS_FOR_RENT",
)


def ruta_listado(categoria_slug: str) -> str:
    """Ruta del listado para un slug conocido, o el slug mismo si es una
    ruta custom (ej. "venta/casa/propiedades-usadas/metropolitana")."""
    if categoria_slug in CATEGORIAS_PRINCIPALES:
        return CATEGORIAS_PRINCIPALES[categoria_slug][0]
    return categoria_slug


def _inferir_tipos(categoria_slug: str) -> tuple[str | None, str | None]:
    """(tipo_operacion, tipo_propiedad) a partir del slug de categoría."""
    if categoria_slug in CATEGORIAS_PRINCIPALES:
        _, tipo_operacion, tipo_propiedad = CATEGORIAS_PRINCIPALES[categoria_slug]
        return (tipo_operacion, tipo_propiedad)
    operacion = None
    if "arriendo" in categoria_slug:
        operacion = "arriendo"
    elif "venta" in categoria_slug:
        operacion = "venta"
    propiedad = None
    if "departamento" in categoria_slug:
        propiedad = "departamento"
    elif "casa" in categoria_slug:
        propiedad = "casa"
    return (operacion, propiedad)


def _cuerpo(componentes: dict[str, dict], tipo: str) -> dict[str, Any]:
    """Cuerpo interno de un componente ({type: X, X: {...}} -> {...})."""
    componente = componentes.get(tipo)
    if not isinstance(componente, dict):
        return {}
    cuerpo = componente.get(tipo)
    return cuerpo if isinstance(cuerpo, dict) else {}


def _parsear_atributos_tarjeta(textos: list[str]) -> dict:
    """["4 dormitorios", "4 baños", "163 m² útiles"] -> campos del registro.

    El m² con sufijo "totales" va a m2_totales (terreno); el resto, a
    m2_tarjeta (equivalente al m² de la tarjeta de Yapo, típicamente
    útiles), que el ETL usa como fallback de m2_util.
    """
    detalles: dict = {
        "m2_tarjeta": None,
        "m2_totales": None,
        "dormitorios": None,
        "banos": None,
        "estacionamientos": None,  # el listado de PI no lo reporta
    }
    for texto in textos:
        texto = texto.strip().lower()
        if "dormitorio" in texto:
            detalles["dormitorios"] = a_entero(texto)
        elif "baño" in texto:
            detalles["banos"] = a_entero(texto)
        elif "m²" in texto or "m2" in texto:
            if "total" in texto:
                detalles["m2_totales"] = parsear_m2(texto)
            else:
                detalles["m2_tarjeta"] = parsear_m2(texto)
    return detalles


def _parsear_descuento(precio: dict[str, Any]) -> float | None:
    """(previous - current) / previous * 100 si el aviso bajó de precio."""
    previo = (precio.get("previous_price") or {}).get("value")
    actual = (precio.get("current_price") or {}).get("value")
    if not previo or not actual:
        return None
    return round((previo - actual) / previo * 100, 1)


def _parsear_polycard(polycard: dict[str, Any], categoria_slug: str) -> dict | None:
    """Parsea un polycard; None si no es un aviso individual."""
    metadata = polycard.get("metadata") or {}
    dominio = metadata.get("domain_id") or ""
    if not str(dominio).startswith(DOMINIOS_INDIVIDUALES):
        return None
    adid = metadata.get("id")
    url = metadata.get("url")
    if not adid or not url:
        return None

    componentes = {
        c.get("type"): c
        for c in polycard.get("components") or []
        if isinstance(c, dict)
    }
    precio = _cuerpo(componentes, "price")
    actual = precio.get("current_price") or {}
    señal = metadata.get("signal") or {}
    valor = actual.get("value", señal.get("price"))
    moneda = actual.get("currency", señal.get("currency"))
    precio_moneda = MONEDAS.get(moneda, moneda)
    precio_valor = a_flotante(valor)

    ubicacion = _cuerpo(componentes, "location").get("text")
    comuna = None
    if ubicacion:
        segmentos = [s.strip() for s in ubicacion.split(",")]
        comuna = segmentos[-1] or None

    vendedor = _cuerpo(componentes, "seller").get("text")
    if vendedor:
        vendedor = vendedor.replace("{icon_cockade}", "").strip() or None

    etiqueta = (polycard.get("float_highlight") or {}).get("text") or (
        polycard.get("featured") or {}
    ).get("text")

    tipo_operacion, tipo_propiedad = _inferir_tipos(categoria_slug)

    registro = {
        "adid": adid,
        "url_origen": url if url.startswith("http") else f"https://{url}",
        "categoria_slug": categoria_slug,
        "tipo_operacion": tipo_operacion,
        "tipo_propiedad": tipo_propiedad,
        "titulo": _cuerpo(componentes, "title").get("text"),
        "precio_texto": formatear_precio(precio_valor, precio_moneda),
        "precio_valor": precio_valor,
        "precio_moneda": precio_moneda,
        "comuna": comuna,
        "vendedor": vendedor,
        "es_profesional": "seller" in componentes,
        "etiqueta": etiqueta,
        "descuento_pct": _parsear_descuento(precio),
    }
    textos = _cuerpo(componentes, "attributes_list").get("texts") or []
    registro.update(_parsear_atributos_tarjeta(textos))
    return registro


def parsear_tarjetas(html: str, categoria_slug: str) -> list[dict]:
    """Extrae los avisos individuales de una página de listado."""
    estado = extraer_estado_inicial(html)
    resultados = estado.get("results")
    if not isinstance(resultados, list):
        return []
    registros = []
    for resultado in resultados:
        if not isinstance(resultado, dict) or resultado.get("id") != "POLYCARD":
            continue  # intervenciones: filtros del sidebar, ads
        polycard = resultado.get("polycard")
        if not isinstance(polycard, dict):
            continue
        registro = _parsear_polycard(polycard, categoria_slug)
        if registro:
            registros.append(registro)
    return registros


def obtener_url_siguiente(html: str) -> str | None:
    """URL de la siguiente página de resultados, o None si es la última."""
    paginacion = extraer_estado_inicial(html).get("pagination") or {}
    siguiente = paginacion.get("next_page") or {}
    url = siguiente.get("url")
    return url if url and siguiente.get("show", True) else None


def parsear_total_resultados(html: str) -> int | None:
    """Total de avisos de la búsqueda (melidata_track.event_data.total)."""
    melidata = extraer_estado_inicial(html).get("melidata_track") or {}
    total = (melidata.get("event_data") or {}).get("total")
    return int(total) if isinstance(total, (int, float)) else None
