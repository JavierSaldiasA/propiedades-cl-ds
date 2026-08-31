"""Parsing de las fichas (páginas de detalle) de TOCTOC.

Funciones puras: reciben el HTML de la ficha y devuelven un dict, sin
tocar red ni disco. A diferencia del listado (API de mapa con arreglos
posicionales), la ficha es server-rendered por Next.js y trae todo el
detalle en el script `__NEXT_DATA__`:

    props.pageProps.initialState.property.property.data

Trampas conocidas:
- `price` (CLP) y `priceUf` (UF) vienen AMBOS siempre, pero uno es el real
  y el otro derivado: en ventas la UF es la real (price = priceUf × UF con
  ruido de float); en arriendos el CLP es el real (priceUf redondeado). La
  moneda real se detecta verificando la aritmética contra el valor de UF
  que trae la propia ficha.
- "Año de construcción: 0" significa desconocido -> None.
- Las etiquetas de characteristics traen espacios/colones inconsistentes
  ("Dormitorios:", "Baños: ") y el valor puede ser texto ("60 m²").
- GeoJSON: coordinates = [longitud, latitud] (orden invertido).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from src.scraping.numeros import (
    a_booleano_si_no,
    a_entero,
    bodega_desde_valor,
    formatear_precio,
    parsear_m2,
    parsear_numero_cl,
)

# etiqueta normalizada de characteristic -> campo del registro
ETIQUETAS_CARACTERISTICAS = {
    "dormitorios": "dormitorios",
    "baños": "banos",
    "superf. útil": "m2_construida",
    "superf. terreno": "m2_totales",
    "superf. terraza": "m2_terraza",
    "gastos comunes": "gastos_comunes",
    "estacionamientos": "estacionamientos",
    "cantidad de pisos": "cantidad_pisos",
    "piso": "piso",
    "año de construcción": "anio_construccion",
    "antigüedad": "antiguedad",
    "bodega": "bodega",
    "bodegas": "bodega",
    "piscina": "piscina",
}


def extraer_data(html: str) -> dict[str, Any]:
    """Dict `data` de la ficha ( initialState.property.property.data ), o {}."""
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        return {}
    try:
        datos = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    propiedad = (
        datos.get("props", {})
        .get("pageProps", {})
        .get("initialState", {})
        .get("property", {})
        .get("property", {})
    )
    data = propiedad.get("data")
    return data if isinstance(data, dict) else {}


def _normalizar_etiqueta(texto: str | None) -> str:
    """'Dormitorios:' -> 'dormitorios' (minúsculas, sin puntos/espacios)."""
    if not texto:
        return ""
    return texto.strip().rstrip(":").strip().lower()


def _parsear_caracteristicas(data: dict[str, Any]) -> dict[str, Any]:
    """Lista de characteristics -> dict campo -> valor crudo (str)."""
    resultado: dict[str, Any] = {}
    for caracteristica in data.get("characteristics") or []:
        if not isinstance(caracteristica, dict):
            continue
        etiqueta = _normalizar_etiqueta(caracteristica.get("name"))
        campo = ETIQUETAS_CARACTERISTICAS.get(etiqueta)
        if campo:
            resultado[campo] = caracteristica.get("value")
    return resultado


def _detectar_moneda(
    precio: float | None, precio_uf: float | None, valor_uf: float | None
) -> tuple[float | None, str | None]:
    """(valor, moneda) reales de publicación.

    Si price ≈ priceUf × UF, la UF es la moneda de publicación (el CLP es
    derivado; típico de ventas). Si no calza, el CLP es el real (la UF vino
    redondeada; típico de arriendos).
    """
    precio = precio or 0
    precio_uf = precio_uf or 0
    valor_uf = valor_uf or 0
    if precio_uf > 0 and valor_uf > 0 and abs(precio_uf * valor_uf - precio) < 1.0:
        return (precio_uf, "UF")
    if precio > 0:
        return (precio, "CLP")
    if precio_uf > 0:
        return (precio_uf, "UF")
    return (None, None)


def _parsear_fecha_iso(texto: str | None) -> datetime | None:
    """ "2026-06-25T00:00:00.000Z" -> date."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.split("T")[0])
    except ValueError:
        return None


def _parsear_bodega(valor: str | None) -> bool | None:
    """ "2" (número de bodegas) o "Sí"/"No" -> bool."""
    return bodega_desde_valor(valor)


def parsear_ficha(html: str) -> dict:
    """Extrae los campos de la ficha de un aviso.

    Las claves con dato ausente vienen en None; el orquestador hace merge
    sobre el registro del listado ignorando los None.
    """
    data = extraer_data(html)
    if not data:
        return {}

    caracteristicas = _parsear_caracteristicas(data)
    operacion = data.get("operation") or {}
    direccion = data.get("address") or {}
    coordenadas = (direccion.get("location") or {}).get("coordinates") or []
    latitud = float(coordenadas[1]) if len(coordenadas) > 1 else None
    longitud = float(coordenadas[0]) if coordenadas else None

    precio_valor, precio_moneda = _detectar_moneda(
        data.get("price"), data.get("priceUf"), data.get("UF")
    )

    anio = a_entero(caracteristicas.get("anio_construccion"))
    if anio == 0:  # "Año de construcción: 0" = desconocido
        anio = None
    if anio is None:  # "Antigüedad: 25 años" -> año estimado
        antiguedad = a_entero(caracteristicas.get("antiguedad"))
        if antiguedad is not None:
            anio = datetime.now().year - antiguedad

    texto_operacion = str(operacion.get("operation") or "")
    precio_texto = formatear_precio(precio_valor, precio_moneda)

    return {
        "adid": str(data.get("idProperty")) if data.get("idProperty") else None,
        "url_origen": data.get("urlPublication"),
        "titulo": data.get("title"),
        "precio_texto": precio_texto,
        "precio_valor": precio_valor,
        "precio_moneda": precio_moneda,
        "comuna": (direccion.get("commune") or None),
        "region": (direccion.get("region") or None),
        "descripcion": data.get("description") or None,
        "vendedor": (data.get("client") or {}).get("name"),
        "es_profesional": "corredor" in texto_operacion.lower(),
        "etiqueta": "Destacada" if operacion.get("highlighted") else None,
        "fecha_publicacion": _parsear_fecha_iso(operacion.get("publicationDate")),
        "dormitorios": a_entero(caracteristicas.get("dormitorios")),
        "banos": a_entero(caracteristicas.get("banos")),
        "estacionamientos": a_entero(caracteristicas.get("estacionamientos")),
        "m2_construida": parsear_m2(caracteristicas.get("m2_construida")),
        "m2_totales": parsear_m2(caracteristicas.get("m2_totales")),
        "gastos_comunes": parsear_numero_cl(caracteristicas.get("gastos_comunes")),
        "anio_construccion": anio,
        "piso": a_entero(caracteristicas.get("piso")),
        "piscina": a_booleano_si_no(caracteristicas.get("piscina")),
        "bodega": _parsear_bodega(caracteristicas.get("bodega")),
        "beneficios": [
            amenidad for amenidad in (data.get("amenities") or []) if amenidad
        ],
        "latitud": latitud,
        "longitud": longitud,
    }
