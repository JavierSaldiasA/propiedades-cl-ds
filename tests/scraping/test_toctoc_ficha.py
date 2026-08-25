"""Tests de src/scraping/toctoc_ficha.py contra HTML real (ver fixtures/)."""

from src.scraping.toctoc_ficha import parsear_ficha


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
