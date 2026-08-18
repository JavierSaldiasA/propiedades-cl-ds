"""Parsing de páginas de detalle de avisos de Yapo.

Funciones puras: reciben HTML como string y devuelven un dict, sin tocar
red ni disco. Selectores verificados contra el HTML real el 2026-08-07.

Fuentes de datos dentro de la página:
- JSON-LD (@type Product): precio numérico, moneda, título limpio.
- Barra insight (dt/dd) y tabla de atributos: dormitorios, baños, m²,
  gastos comunes, año de construcción, fecha de publicación, etc.
  Las filas sin dato ("¡Pregunta al anunciante!") se omiten -> None.
- Breadcrumb inferior: región (penúltimo link) y comuna (último link).
- iframe del mapa: coordenadas lat/lon.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.scraping.numeros import parsear_numero_cl

# Yapo usa códigos ISO 4217 en el JSON-LD: la UF aparece como "CLF".
# Se normaliza al vocabulario del proyecto ("UF"/"CLP", ver schema.sql).
MONEDAS_JSONLD = {"CLF": "UF"}


def _parsear_jsonld(sopa: BeautifulSoup) -> dict:
    """Primer bloque JSON-LD de tipo Product (hay otros, ej. Organization)."""
    for script in sopa.select('script[type="application/ld+json"]'):
        try:
            datos = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict) and datos.get("@type") == "Product":
            return datos
    return {}


def _parsear_atributos(sopa: BeautifulSoup) -> dict[str, str]:
    """Atributos etiqueta -> valor, combinando la barra insight y la tabla."""
    atributos: dict[str, str] = {}
    for atributo in sopa.select("div.d3-property-insight__attribute"):
        etiqueta = atributo.select_one("dt.d3-property-insight__attribute-title")
        valor = atributo.select_one("dd.d3-property-insight__attribute-value")
        if etiqueta and valor:
            atributos[etiqueta.get_text(strip=True)] = valor.get_text(strip=True)
    for fila in sopa.select("div.d3-property-details__detail-label"):
        etiqueta = fila.find(string=True, recursive=False)
        valor = fila.select_one("p.d3-property-details__detail")
        if not etiqueta or valor is None:
            continue
        if valor.select_one("a.quickmessage-cta"):
            continue  # sin dato: "¡Pregunta al anunciante!"
        atributos[etiqueta.strip()] = valor.get_text(strip=True)
    return atributos


def _parsear_beneficios(sopa: BeautifulSoup) -> list[str]:
    return [
        beneficio.get_text(strip=True)
        for beneficio in sopa.select(
            "div.d3-property-benefits div.d3-property-benefits__benefit"
        )
    ]


def _parsear_breadcrumb(sopa: BeautifulSoup) -> tuple[str | None, str | None]:
    """(region, comuna) desde el breadcrumb inferior de la página."""
    miga = sopa.select_one("div.d3-property-breadcrumbcatandregion ol.breadcrumb")
    if not miga:
        return (None, None)
    textos = [li.get_text(strip=True) for li in miga.select("li") if li.find("a")]
    if len(textos) < 3:
        return (None, None)
    return (textos[-2], textos[-1])


def _parsear_coordenadas(sopa: BeautifulSoup) -> tuple[float | None, float | None]:
    iframe = sopa.select_one("section.d3-property__map iframe[src]")
    if not iframe:
        return (None, None)
    coincidencia = re.search(r"q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", iframe["src"])
    if not coincidencia:
        return (None, None)
    return (float(coincidencia.group(1)), float(coincidencia.group(2)))


def _localidad_jsonld(oferta: dict) -> str | None:
    lugar = oferta.get("availableAtOrFrom")
    if not isinstance(lugar, dict):
        return None
    direccion = lugar.get("address")
    if not isinstance(direccion, dict):
        return None
    return direccion.get("addressLocality")


def _a_entero(texto: str | None) -> int | None:
    numero = parsear_numero_cl(texto)
    return int(numero) if numero is not None else None


def _a_flotante(texto: str | None) -> float | None:
    """float() None-safe para atributos del detalle en formato US.

    Los m² del detalle vienen en formato US (punto = decimal: "80.5"),
    a diferencia de los precios (es-CL) -> NO usar parsear_numero_cl aquí.
    """
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _a_booleano_si_no(texto: str | None) -> bool | None:
    if not texto:
        return None
    limpio = texto.strip().lower()
    if limpio in ("si", "sí"):
        return True
    if limpio == "no":
        return False
    return None


def _parsear_fecha(texto: str | None) -> date | None:
    """Fecha "dd/mm/yyyy" -> date. None si no calza."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def parsear_detalle(html: str) -> dict:
    """Extrae los campos de la página de detalle de un aviso.

    Las claves con dato ausente vienen en None; el orquestador hace merge
    sobre el registro de la tarjeta ignorando los None.
    """
    sopa = BeautifulSoup(html, "html.parser")
    jsonld = _parsear_jsonld(sopa)
    oferta = jsonld.get("offers", {})
    if not isinstance(oferta, dict):
        oferta = {}
    atributos = _parsear_atributos(sopa)
    region, comuna = _parsear_breadcrumb(sopa)
    latitud, longitud = _parsear_coordenadas(sopa)
    beneficios = _parsear_beneficios(sopa)

    descripcion_el = sopa.select_one("div.d3-property-about__text")
    precio = oferta.get("price")
    moneda = oferta.get("priceCurrency")

    return {
        "titulo": jsonld.get("name"),
        "precio_valor": float(precio) if precio is not None else None,
        "precio_moneda": MONEDAS_JSONLD.get(moneda, moneda),
        "comuna": comuna or _localidad_jsonld(oferta),
        "region": region,
        "descripcion": (
            descripcion_el.get_text(separator="\n", strip=True)
            if descripcion_el
            else None
        ),
        "beneficios": beneficios,
        "bodega": (
            any("bodega" in beneficio.lower() for beneficio in beneficios)
            if beneficios
            else None
        ),
        "fecha_publicacion": _parsear_fecha(atributos.get("Publicado")),
        "dormitorios": _a_entero(atributos.get("Dormitorios")),
        "banos": _a_entero(atributos.get("Baños")),
        "estacionamientos": _a_entero(atributos.get("Estacionamientos")),
        "m2_construida": _a_flotante(atributos.get("Área construida (m²)")),
        "m2_totales": _a_flotante(atributos.get("M² totales")),
        "gastos_comunes": parsear_numero_cl(atributos.get("Gastos comunes")),
        "anio_construccion": _a_entero(atributos.get("Años de construcción")),
        "piso": _a_entero(atributos.get("Piso Número")),
        "piscina": _a_booleano_si_no(atributos.get("Piscina")),
        "latitud": latitud,
        "longitud": longitud,
    }
