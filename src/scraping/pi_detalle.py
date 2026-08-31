"""Parsing de páginas de detalle (VIP) de Portal Inmobiliario.

Funciones puras: reciben HTML como string y devuelven un dict, sin tocar
red ni disco. Los datos viven en el JSON `__NORDIC_RENDERING_CTX__`
(`appProps.pageProps.initialState`).

El layout de la VIP varía según el tipo de aviso (p. ej.
"vip-real-estate-ltr-new-experience", "vip-real-estate-new-experience") y
los componentes cambian de nombre según la versión (description vs
description_rex, specs anidadas en highlighted_specs_attrs_new): en vez de
seguir rutas fijas, los componentes se buscan por id de forma recursiva.

Trampas conocidas:
- No hay fecha de publicación: solo texto relativo ("Publicado esta
  semana") en el encabezado -> se deja None y el ETL usa fecha_scraping.
- Las coordenadas vienen como strings.
- Los m² usan separadores mixtos según el componente: coma decimal es-CL
  ("37,54") o punto US ("63.1") -> ver numeros.parsear_m2.
- La UF llega como "CLF" (ISO 4217).
- "Antigüedad" viene en años ("54 años"): se deriva anio_construccion
  como año actual - años.
- Los atributos no traen ids de máquina: las etiquetas son texto en
  español ("Superficie útil", "Bodegas", ...).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from src.scraping.numeros import (
    a_booleano_si_no,
    a_entero,
    a_flotante,
    a_flotante_cl,
    bodega_desde_valor,
    parsear_m2,
)
from src.scraping.pi_nordic import extraer_estado_inicial

# La UF llega como "CLF" (código ISO 4217 de Mercado Libre).
MONEDAS = {"CLF": "UF"}


def _buscar_componente(nodo: Any, id_componente: str) -> dict[str, Any] | None:
    """Primer dict del árbol JSON con id == id_componente.

    Busca de forma recursiva (los componentes viven en grupos, aplanados
    y a veces anidados dentro de otros componentes) y exige que el dict
    parezca un componente (tenga type o state) para no confundirlo con
    ids internos (iconos, imágenes).
    """
    if isinstance(nodo, dict):
        if nodo.get("id") == id_componente and ("type" in nodo or "state" in nodo):
            return nodo
        for valor in nodo.values():
            encontrado = _buscar_componente(valor, id_componente)
            if encontrado is not None:
                return encontrado
    elif isinstance(nodo, list):
        for elemento in nodo:
            encontrado = _buscar_componente(elemento, id_componente)
            if encontrado is not None:
                return encontrado
    return None


def _parsear_precio(estado: dict[str, Any]) -> tuple[float | None, str | None]:
    """(valor, moneda) del componente price, con fallback al JSON-LD."""
    precio = (_buscar_componente(estado, "price") or {}).get("price") or {}
    valor = precio.get("value")
    moneda = precio.get("currency_id")
    if valor is None:
        for esquema in estado.get("schema") or []:
            if isinstance(esquema, dict) and esquema.get("@type") == "Product":
                oferta = esquema.get("offers") or {}
                valor = oferta.get("price")
                moneda = oferta.get("priceCurrency")
    return (
        float(valor) if valor is not None else None,
        MONEDAS.get(moneda, moneda),
    )


def _parsear_atributos(estado: dict[str, Any]) -> dict[str, str]:
    """Atributos etiqueta -> valor desde technical_specifications."""
    componente = _buscar_componente(estado, "technical_specifications") or {}
    atributos: dict[str, str] = {}
    for spec in componente.get("specs") or []:
        for atributo in spec.get("attributes") or []:
            etiqueta = atributo.get("id")
            texto = atributo.get("text")
            if isinstance(etiqueta, str) and isinstance(texto, str):
                atributos[etiqueta.strip()] = texto.strip()
    return atributos


def _parsear_ubicacion(
    estado: dict[str, Any],
) -> tuple[str | None, str | None, float | None, float | None]:
    """(region, comuna, latitud, longitud) desde el componente de mapa."""
    componente = (
        _buscar_componente(estado, "location_and_points")
        or _buscar_componente(estado, "location")
        or {}
    )
    map_info = componente.get("map_info") or {}
    location = map_info.get("location") or {}
    latitud = a_flotante(location.get("latitude"))
    longitud = a_flotante(location.get("longitude"))
    # item_location: "Las Condes, RM (Metropolitana)" -> comuna, región
    item_location = map_info.get("item_location") or ""
    segmentos = [s.strip() for s in item_location.split(",")]
    comuna = segmentos[0] or None
    region = segmentos[1] if len(segmentos) > 1 else None
    return (region, comuna, latitud, longitud)


def _parsear_descripcion(estado: dict[str, Any]) -> str | None:
    componente = (
        _buscar_componente(estado, "description_rex")
        or _buscar_componente(estado, "description")
        or {}
    )
    return componente.get("content")


def _parsear_vendedor(estado: dict[str, Any]) -> str | None:
    componente = (
        _buscar_componente(estado, "seller_profile_rex")
        or _buscar_componente(estado, "seller_profile")
        or {}
    )
    return ((componente.get("seller_name") or {}).get("title") or {}).get("text")


def _parsear_bodega(atributos: dict[str, str]) -> bool | None:
    """ "Bodegas: 1" (o "Bodega: Sí") -> bool."""
    for etiqueta in ("Bodegas", "Bodega"):
        texto = atributos.get(etiqueta)
        if texto is None:
            continue
        return bodega_desde_valor(texto)
    return None


def _parsear_anio_construccion(texto: str | None) -> int | None:
    """ "Antigüedad: 54 años" -> año de construcción estimado."""
    if not texto:
        return None
    coincidencia = re.search(r"\d+", texto)
    if not coincidencia:
        return None
    return datetime.now().year - int(coincidencia.group())


def parsear_detalle(html: str) -> dict:
    """Extrae los campos de la página de detalle de un aviso.

    Las claves con dato ausente vienen en None; el orquestador hace merge
    sobre el registro de la tarjeta ignorando los None.
    """
    estado = extraer_estado_inicial(html)
    atributos = _parsear_atributos(estado)
    region, comuna, latitud, longitud = _parsear_ubicacion(estado)
    precio_valor, precio_moneda = _parsear_precio(estado)
    beneficios = [etiqueta for etiqueta, texto in atributos.items() if texto == "Sí"]

    return {
        "precio_valor": precio_valor,
        "precio_moneda": precio_moneda,
        "comuna": comuna,
        "region": region,
        "descripcion": _parsear_descripcion(estado),
        "vendedor": _parsear_vendedor(estado),
        "beneficios": beneficios,
        "bodega": _parsear_bodega(atributos),
        "dormitorios": a_entero(atributos.get("Dormitorios")),
        "banos": a_entero(atributos.get("Baños")),
        "estacionamientos": a_entero(atributos.get("Estacionamientos")),
        "m2_construida": parsear_m2(atributos.get("Superficie útil")),
        "m2_totales": parsear_m2(atributos.get("Superficie total")),
        "gastos_comunes": a_flotante_cl(atributos.get("Gastos comunes")),
        "anio_construccion": _parsear_anio_construccion(atributos.get("Antigüedad")),
        "piso": a_entero(atributos.get("Número de piso de la unidad")),
        "piscina": a_booleano_si_no(atributos.get("Piscina")),
        "latitud": latitud,
        "longitud": longitud,
    }
