"""Tests de src/scraping/toctoc_ficha.py contra HTML real (ver fixtures/)."""

import json

from src.scraping.toctoc_ficha import parsear_ficha


def _html_con_data(data: dict) -> str:
    estado = {"property": {"property": {"data": data}}}
    payload = {"props": {"pageProps": {"initialState": estado}}}
    return (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    )


def test_parsear_ficha_venta_particular(html_toctoc_ficha_venta):
    """Ficha de depto. en venta de particular (UF, Santiago)."""
    ficha = parsear_ficha(html_toctoc_ficha_venta)
    assert ficha["adid"] == "4231011"
    assert ficha["titulo"] == "Departamento, Libertad 1473 1522"
    # moneda real: price (118.507.195) = priceUf (2.900) x UF (40.864,55)
    assert ficha["precio_valor"] == 2900
    assert ficha["precio_moneda"] == "UF"
    assert ficha["precio_texto"] == "UF 2.900"
    assert ficha["comuna"] == "Santiago"
    assert ficha["region"] == "Metropolitana"
    assert ficha["dormitorios"] == 2
    assert ficha["banos"] == 2
    assert ficha["m2_construida"] == 60.0  # "Superf. útil: 60 m²"
    assert ficha["m2_totales"] is None  # depto. sin terreno
    assert ficha["latitud"] == -33.427746  # GeoJSON: [lon, lat]
    assert ficha["longitud"] == -70.67519
    assert ficha["es_profesional"] is False  # "Venta Usado Particular"
    assert str(ficha["fecha_publicacion"].date()) == "2026-06-25"
    assert "estación de metro Matucana" in ficha["descripcion"]


def test_parsear_ficha_arriendo_corredora(html_toctoc_ficha_arriendo):
    """Ficha de depto. en arriendo de corredora (CLP, La Florida)."""
    ficha = parsear_ficha(html_toctoc_ficha_arriendo)
    assert ficha["adid"] == "4281040"
    # moneda real CLP: priceUf (7) es la conversión redondeada, no calza
    # con price / UF
    assert ficha["precio_valor"] == 300000
    assert ficha["precio_moneda"] == "CLP"
    assert ficha["precio_texto"] == "$ 300.000"
    assert ficha["comuna"] == "La Florida"
    assert ficha["region"] == "Metropolitana"
    assert ficha["dormitorios"] == 1
    assert ficha["banos"] == 2
    assert ficha["m2_construida"] == 34.38  # decimal US en "34.38 m²"
    assert ficha["es_profesional"] is True  # "Arriendo Usado Corredor"
    assert str(ficha["fecha_publicacion"].date()) == "2026-07-23"
    assert "metro Macul" in ficha["titulo"]


def test_parsear_ficha_anio_construccion_cero_es_none(
    html_toctoc_ficha_arriendo,
):
    """ "Año de construcción: 0" significa desconocido -> None."""
    ficha = parsear_ficha(html_toctoc_ficha_arriendo)
    assert ficha["anio_construccion"] is None


def test_parsear_ficha_url_canonica_con_hash(html_toctoc_ficha_arriendo):
    """La ficha reporta urlPublication con hash: se expone tal cual y el
    orquestador decide no sobrescribir la URL del listado."""
    ficha = parsear_ficha(html_toctoc_ficha_arriendo)
    assert ficha["url_origen"].endswith("01e5ac14622e984557ca85b99dba4da2b202fddb")


def test_parsear_ficha_html_sin_datos():
    assert parsear_ficha("<html><body>Vacío</body></html>") == {}


def test_parsear_ficha_anio_determinista_con_anio_inyectado():
    """ "Antigüedad: 25 años" -> anio_construccion no depende del reloj."""
    html = _html_con_data(
        {
            "characteristics": [{"name": "Antigüedad:", "value": "25 años"}],
            "operation": {"operation": "Venta"},
        }
    )
    ficha = parsear_ficha(html, anio_actual=2026)
    assert ficha["anio_construccion"] == 2001
    ficha_2020 = parsear_ficha(html, anio_actual=2020)
    assert ficha_2020["anio_construccion"] == 1995


def test_parsear_ficha_coordenadas_como_texto():
    """Las coordenadas del GeoJSON como strings no las rompen."""
    html = _html_con_data(
        {
            "address": {"location": {"coordinates": ["-70.67519", "-33.427746"]}},
            "operation": {"operation": "Venta"},
        }
    )
    ficha = parsear_ficha(html)
    assert ficha["latitud"] == -33.427746
    assert ficha["longitud"] == -70.67519


def test_parsear_ficha_coordenadas_malformadas_no_rompen():
    """Coordenadas no numéricas caen a None en vez de lanzar ValueError."""
    html = _html_con_data(
        {
            "address": {"location": {"coordinates": ["sin-dato", "sin-dato"]}},
            "operation": {"operation": "Venta"},
        }
    )
    ficha = parsear_ficha(html)
    assert ficha["latitud"] is None
    assert ficha["longitud"] is None


def test_parsear_ficha_etiquetas_no_mapeadas_y_m2_como_texto():
    """Etiquetas no usadas (p. ej. "Superf. terraza") no rompen el parseo, y
    m² con unidades ("60 m²") se convierten igual."""
    html = _html_con_data(
        {
            "characteristics": [
                {"name": "Superf. útil:", "value": "60 m²"},
                {"name": "Superf. terraza:", "value": "8 m²"},
                {"name": "Cantidad de pisos:", "value": "2"},
                {"name": "Etiqueta desconocida:", "value": "x"},
            ],
            "operation": {"operation": "Venta"},
        }
    )
    ficha = parsear_ficha(html)
    assert ficha["m2_construida"] == 60.0
    assert ficha["dormitorios"] is None
    assert ficha["anio_construccion"] is None
