"""Parsing de páginas de listado de Yapo.

Funciones puras: reciben HTML como string y devuelven dicts, sin tocar red
ni disco.

Selectores verificados contra el HTML real el 2026-08-07.
Trampas conocidas:
- El atributo data-price de las tarjetas está en USD: NO usar como precio.
- Los ítems de detalle (m²/dorm/baños/estac.) vienen en orden variable:
  se identifican por el ícono SVG (#resize/#bed/#bath/#parking).
- La paginación aparece duplicada (arriba y abajo de la página).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.scraping.numeros import parsear_numero_cl, parsear_precio_texto

BASE_URL = "https://www.yapo.cl"

# Slugs de las 4 categorías principales -> (tipo_operacion, tipo_propiedad)
CATEGORIAS_PRINCIPALES: dict[str, tuple[str, str]] = {
    "bienes-raices-venta-de-propiedades-casas": ("venta", "casa"),
    "bienes-raices-venta-de-propiedades-apartamentos": ("venta", "departamento"),
    "bienes-raices-alquiler-casas": ("arriendo", "casa"),
    "bienes-raices-alquiler-apartamentos": ("arriendo", "departamento"),
}

# Fragmento del ícono SVG (tras el #) -> campo del registro
ICONOS_DETALLE = {
    "resize": "m2_tarjeta",
    "bed": "dormitorios",
    "bath": "banos",
    "parking": "estacionamientos",
}


def _inferir_tipos(categoria_slug: str) -> tuple[str | None, str | None]:
    """(tipo_operacion, tipo_propiedad) a partir del slug de categoría."""
    if categoria_slug in CATEGORIAS_PRINCIPALES:
        return CATEGORIAS_PRINCIPALES[categoria_slug]
    if "alquiler" in categoria_slug:
        return ("arriendo", None)
    if "venta" in categoria_slug:
        return ("venta", None)
    return (None, None)


def _parsear_detalles_tarjeta(tarjeta: Tag) -> dict:
    """Extrae m²/dormitorios/baños/estacionamientos identificando por ícono."""
    detalles: dict = {
        "m2_tarjeta": None,
        "dormitorios": None,
        "banos": None,
        "estacionamientos": None,
    }
    for item in tarjeta.select("li.d3-ad-tile__details-item"):
        uso = item.find("use")
        if not uso:
            continue
        href = uso.get("xlink:href") or uso.get("href") or ""
        campo = ICONOS_DETALLE.get(href.split("#")[-1])
        if not campo:
            continue
        texto = item.get_text(strip=True)  # ej. "57 m2" o "3"
        coincidencia = re.search(r"[\d\.,]+", texto)
        numero = parsear_numero_cl(coincidencia.group()) if coincidencia else None
        if numero is None:
            continue
        detalles[campo] = numero if campo == "m2_tarjeta" else int(numero)
    return detalles


def _parsear_descuento(tarjeta: Tag) -> float | None:
    """Porcentaje de descuento del badge "-19%" (como magnitud positiva)."""
    reduccion = tarjeta.select_one(".d3-ad-tile__price-reduction")
    if not reduccion:
        return None
    coincidencia = re.search(r"[\d\.,]+", reduccion.get_text(strip=True))
    return parsear_numero_cl(coincidencia.group()) if coincidencia else None


def _parsear_tarjeta(tarjeta: Tag, categoria_slug: str) -> dict | None:
    """Parsea una tarjeta; None si no es un aviso de la categoría pedida."""
    enlace = tarjeta.select_one("a.d3-ad-tile__description[href]")
    if not enlace:
        return None
    href = enlace["href"]
    if not href.startswith(f"/{categoria_slug}/"):
        # En listados genéricos el grid mezcla subcategorías: se filtran
        return None
    adid = href.rstrip("/").rsplit("/", 1)[-1]

    titulo_el = tarjeta.select_one("span.d3-ad-tile__title")
    precio_div = tarjeta.select_one("div.d3-ad-tile__price")
    # El hallmark y el badge de descuento viven DENTRO del div de precio:
    # solo se toma el texto directo
    nodo_precio = precio_div.find(string=True, recursive=False) if precio_div else None
    precio_texto = nodo_precio.strip() if nodo_precio else ""
    precio_valor, precio_moneda = parsear_precio_texto(precio_texto)

    ubicacion_el = tarjeta.select_one("div.d3-ad-tile__location")
    vendedor_el = tarjeta.select_one(".d3-ad-tile__seller > span")
    etiqueta_el = tarjeta.select_one(".d3-ad-tile__hallmark")

    tipo_operacion, tipo_propiedad = _inferir_tipos(categoria_slug)

    registro = {
        "adid": adid,
        "url_origen": urljoin(BASE_URL, href),
        "categoria_slug": categoria_slug,
        "tipo_operacion": tipo_operacion,
        "tipo_propiedad": tipo_propiedad,
        "titulo": titulo_el.get_text(strip=True) if titulo_el else None,
        "precio_texto": precio_texto or None,
        "precio_valor": precio_valor,
        "precio_moneda": precio_moneda,
        "comuna": ubicacion_el.get_text(strip=True) if ubicacion_el else None,
        "vendedor": vendedor_el.get_text(strip=True) if vendedor_el else None,
        "es_profesional": tarjeta.select_one(
            ".d3-ad-tile__seals img[title='Profesional']"
        )
        is not None,
        "etiqueta": etiqueta_el.get_text(strip=True) if etiqueta_el else None,
        "descuento_pct": _parsear_descuento(tarjeta),
    }
    registro.update(_parsear_detalles_tarjeta(tarjeta))
    return registro


def parsear_tarjetas(html: str, categoria_slug: str) -> list[dict]:
    """Extrae los avisos de una página de listado (solo de la categoría dada)."""
    sopa = BeautifulSoup(html, "html.parser")
    registros = []
    for tarjeta in sopa.select("div.d3-ads-grid > div.d3-ad-tile"):
        registro = _parsear_tarjeta(tarjeta, categoria_slug)
        if registro:
            registros.append(registro)
    return registros


def obtener_url_siguiente(html: str) -> str | None:
    """URL de la siguiente página de resultados, o None si es la última."""
    sopa = BeautifulSoup(html, "html.parser")
    enlace = sopa.select_one("a.d3-pagination__arrow--next[href]")
    return urljoin(BASE_URL, enlace["href"]) if enlace else None


def parsear_total_resultados(html: str) -> int | None:
    """Total de avisos del listado ('Encontramos 21.598 ...' -> 21598)."""
    sopa = BeautifulSoup(html, "html.parser")
    encabezado = sopa.select_one("h2.d3-category-list__results")
    if not encabezado:
        return None
    coincidencia = re.search(r"Encontramos ([\d\.]+)", encabezado.get_text())
    return int(coincidencia.group(1).replace(".", "")) if coincidencia else None
