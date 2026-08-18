"""Tests de src/scraping/yapo_detalle.py contra HTML real (aviso 32632138)."""

from datetime import date

import pytest

from src.scraping.yapo_detalle import parsear_detalle


@pytest.fixture
def detalle(html_detalle):
    return parsear_detalle(html_detalle)


def test_precio_desde_jsonld(detalle):
    assert detalle["precio_valor"] == 450000.0
    assert detalle["precio_moneda"] == "CLP"


def test_titulo_limpio_sin_prefijo_seo(detalle):
    assert detalle["titulo"] == "Departamento en arriendo 3D/2B Metro Ñuble"


def test_region_y_comuna(detalle):
    assert detalle["region"] == "Región Metropolitana"
    assert detalle["comuna"] == "Santiago"


def test_atributos_numericos(detalle):
    assert detalle["dormitorios"] == 3
    assert detalle["banos"] == 2
    assert detalle["m2_construida"] == 55.0
    assert detalle["m2_totales"] == 55.0
    assert detalle["gastos_comunes"] == 85000.0
    assert detalle["anio_construccion"] == 2008
    assert detalle["piso"] == 2


def test_atributo_oculto_es_none(detalle):
    """'Estacionamientos' viene como '¡Pregunta al anunciante!' -> None."""
    assert detalle["estacionamientos"] is None


def test_piscina_si_a_booleano(detalle):
    assert detalle["piscina"] is True


def test_fecha_publicacion(detalle):
    assert detalle["fecha_publicacion"] == date(2026, 7, 30)


def test_descripcion(detalle):
    assert detalle["descripcion"].startswith(
        "DEPARTAMENTO EN ARRIENDO EN CONDOMINIO METRO ÑUBLE"
    )
    assert len(detalle["descripcion"]) > 1000


def test_beneficios_y_bodega(detalle):
    assert detalle["beneficios"] == [
        "Calentador de agua",
        "2 o más ascensores",
        "En condominio",
        "Cocina amoblada",
    ]
    assert detalle["bodega"] is False


def test_coordenadas(detalle):
    assert detalle["latitud"] == pytest.approx(-33.4664124)
    assert detalle["longitud"] == pytest.approx(-70.6280712)


def test_moneda_clf_se_normaliza_a_uf():
    """El JSON-LD usa el código ISO "CLF" para la UF: se normaliza a "UF"."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Casa en venta",
     "offers": {"@type": "Offer", "price": 6900.0, "priceCurrency": "CLF"}}
    </script>
    </head><body></body></html>
    """
    detalle = parsear_detalle(html)
    assert detalle["precio_valor"] == 6900.0
    assert detalle["precio_moneda"] == "UF"
    # El resto de secciones ausentes deben quedar en None / vacío
    assert detalle["comuna"] is None
    assert detalle["beneficios"] == []
    assert detalle["bodega"] is None


def test_m2_formato_us_y_ausencia_no_crashea():
    """Los m² del detalle vienen en formato US (punto decimal) y los
    atributos ausentes deben quedar en None, no lanzar excepción."""
    html = """
    <html><body>
    <div class="d3-property-details">
      <div class="d3-property-details__detail-label">
        Área construida (m²)
        <p class="d3-property-details__detail">80.5</p>
      </div>
      <div class="d3-property-details__detail-label quickmessage-info">
        M² totales
        <p class="d3-property-details__detail">
          <a href="#" class="quickmessage-cta">¡Pregunta al anunciante!</a>
        </p>
      </div>
    </div>
    </body></html>
    """
    detalle = parsear_detalle(html)
    assert detalle["m2_construida"] == 80.5
    assert detalle["m2_totales"] is None
