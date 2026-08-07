"""Tests de src/scraping/yapo_listado.py contra HTML real (ver fixtures/)."""

from src.scraping.yapo_listado import (
    obtener_url_siguiente,
    parsear_tarjetas,
    parsear_total_resultados,
)

CATEGORIA = "bienes-raices-alquiler-apartamentos"


def test_parsear_tarjetas_extrae_todas(html_listado):
    tarjetas = parsear_tarjetas(html_listado, CATEGORIA)
    assert len(tarjetas) == 30
    assert len({t["adid"] for t in tarjetas}) == 30  # sin duplicados


def test_parsear_tarjetas_primera_tarjeta(html_listado):
    tarjeta = parsear_tarjetas(html_listado, CATEGORIA)[0]
    assert tarjeta["adid"] == "32760727"
    assert tarjeta["url_origen"] == (
        "https://www.yapo.cl/bienes-raices-alquiler-apartamentos/"
        "exclusivo-dpto-el-golf-terraza-60m2-sin-vecinos-3d-serv-estac-bodega"
        "-metro-el-golf/32760727"
    )
    assert tarjeta["categoria_slug"] == CATEGORIA
    assert tarjeta["tipo_operacion"] == "arriendo"
    assert tarjeta["tipo_propiedad"] == "departamento"
    assert "Metro El Golf" in tarjeta["titulo"]
    assert tarjeta["precio_texto"] == "UF42,00"
    assert tarjeta["precio_valor"] == 42.0
    assert tarjeta["precio_moneda"] == "UF"
    assert tarjeta["comuna"] == "Las Condes"
    assert tarjeta["m2_tarjeta"] == 57.0
    assert tarjeta["dormitorios"] == 3
    assert tarjeta["banos"] == 2
    assert tarjeta["estacionamientos"] == 1
    assert tarjeta["vendedor"] == "Patricia Rojas Barranti"
    assert tarjeta["es_profesional"] is True
    assert tarjeta["etiqueta"] is None
    assert tarjeta["descuento_pct"] is None


def test_parsear_tarjetas_precio_clp_con_descuento(html_listado):
    tarjeta = parsear_tarjetas(html_listado, CATEGORIA)[1]
    assert tarjeta["precio_moneda"] == "CLP"
    assert tarjeta["precio_valor"] == 350000.0
    assert tarjeta["descuento_pct"] == 19.0


def test_parsear_tarjetas_hallmark(html_listado):
    tarjeta = parsear_tarjetas(html_listado, CATEGORIA)[3]
    assert tarjeta["etiqueta"] == "Oportunidad"
    assert tarjeta["precio_moneda"] == "UF"
    assert tarjeta["precio_valor"] == 100.0


def test_parsear_tarjetas_filtra_categoria_en_listado_mixto(html_listado_mixto):
    """El listado genérico mezcla subcategorías: solo quedan las pedidas."""
    tarjetas = parsear_tarjetas(html_listado_mixto, CATEGORIA)
    assert len(tarjetas) == 6
    assert all(t["tipo_operacion"] == "arriendo" for t in tarjetas)

    tarjetas_venta = parsear_tarjetas(
        html_listado_mixto, "bienes-raices-venta-de-propiedades-casas"
    )
    assert len(tarjetas_venta) == 2
    assert all(t["tipo_propiedad"] == "casa" for t in tarjetas_venta)


def test_obtener_url_siguiente(html_listado, html_listado_mixto):
    assert obtener_url_siguiente(html_listado) == (
        "https://www.yapo.cl/bienes-raices-alquiler-apartamentos.2"
    )
    assert obtener_url_siguiente(html_listado_mixto) == (
        "https://www.yapo.cl/searchresult/bienes-raices.2"
    )


def test_obtener_url_siguiente_sin_paginacion(html_detalle):
    assert obtener_url_siguiente(html_detalle) is None


def test_parsear_total_resultados(html_listado, html_listado_mixto):
    assert parsear_total_resultados(html_listado) == 21598
    assert parsear_total_resultados(html_listado_mixto) == 146479
