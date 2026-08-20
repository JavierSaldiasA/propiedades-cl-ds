"""Tests de src/scraping/pi_listado.py contra HTML real (ver fixtures/)."""

import json

from src.scraping.pi_listado import (
    obtener_url_siguiente,
    parsear_tarjetas,
    parsear_total_resultados,
)

CATEGORIA = "venta-casa"


def _html_con_estado(estado: dict) -> str:
    payload = {"appProps": {"pageProps": {"initialState": estado}}}
    return (
        '<html><script id="__NORDIC_RENDERING_CTX__">'
        f"_n.ctx.r={json.dumps(payload)};_n.ctx.r.assets.manifest=new Map([]);"
        "</script></html>"
    )


def _polycard(
    adid="MLC1",
    dominio="MLC-INDIVIDUAL_HOUSES_FOR_SALE",
    url="portalinmobiliario.com/MLC-1-casa-bonita-_JM",
    precio=100,
    moneda="CLF",
    previo=None,
    textos=None,
    ubicacion="Barrio, Comuna",
    vendedor=None,
) -> dict:
    precio_comp: dict = {"current_price": {"value": precio, "currency": moneda}}
    if previo is not None:
        precio_comp["previous_price"] = {"value": previo, "currency": moneda}
    componentes = [
        {"type": "headline", "headline": {"text": "Casa en venta"}},
        {"type": "title", "title": {"text": "Casa bonita"}},
        {"type": "price", "price": precio_comp},
        {"type": "attributes_list", "attributes_list": {"texts": textos or []}},
        {"type": "location", "location": {"text": ubicacion}},
    ]
    if vendedor:
        componentes.append(
            {"type": "seller", "seller": {"text": vendedor + " {icon_cockade}"}}
        )
    return {
        "id": "POLYCARD",
        "state": "VISIBLE",
        "polycard": {
            "metadata": {
                "id": adid,
                "url": url,
                "signal": {"price": precio, "currency": moneda},
                "domain_id": dominio,
            },
            "components": componentes,
        },
    }


# ---------- HTML real ----------


def test_parsear_tarjetas_extrae_todas(html_pi_listado):
    tarjetas = parsear_tarjetas(html_pi_listado, CATEGORIA)
    assert len(tarjetas) == 48
    assert len({t["adid"] for t in tarjetas}) == 48  # sin duplicados


def test_parsear_tarjetas_primera_tarjeta(html_pi_listado):
    tarjeta = parsear_tarjetas(html_pi_listado, CATEGORIA)[0]
    assert tarjeta["adid"] == "MLC4344772628"
    assert tarjeta["url_origen"] == (
        "https://portalinmobiliario.com/MLC-4344772628-venta-casa-casa-"
        "remodelada-a-pasos-alto-las-condes-_JM"
    )
    assert tarjeta["categoria_slug"] == CATEGORIA
    assert tarjeta["tipo_operacion"] == "venta"
    assert tarjeta["tipo_propiedad"] == "casa"
    assert "Remodelada" in tarjeta["titulo"]
    assert tarjeta["precio_texto"] == "UF 16.950"
    assert tarjeta["precio_valor"] == 16950.0
    assert tarjeta["precio_moneda"] == "UF"  # CLF normalizado
    assert tarjeta["comuna"] == "Las Condes"
    assert tarjeta["m2_tarjeta"] == 163.0
    assert tarjeta["m2_totales"] is None
    assert tarjeta["dormitorios"] == 4
    assert tarjeta["banos"] == 4
    assert tarjeta["estacionamientos"] is None
    assert tarjeta["vendedor"] == "ENTRE PROPIEDADES"  # sin {icon_cockade}
    assert tarjeta["es_profesional"] is True
    assert tarjeta["etiqueta"] == "PUBLICADO ESTA SEMANA"
    assert tarjeta["descuento_pct"] is None


def test_parsear_tarjetas_precio_clp(html_pi_listado):
    tarjetas = {t["adid"]: t for t in parsear_tarjetas(html_pi_listado, CATEGORIA)}
    tarjeta = tarjetas["MLC2172802539"]
    assert tarjeta["precio_moneda"] == "CLP"
    assert tarjeta["precio_valor"] == 270000000.0
    assert tarjeta["precio_texto"] == "$ 270.000.000"
    assert tarjeta["comuna"] == "Las Cabras"
    assert tarjeta["es_profesional"] is False


def test_parsear_tarjetas_sin_vendedor(html_pi_listado):
    """Los avisos de particulares no traen componente seller."""
    tarjetas = parsear_tarjetas(html_pi_listado, CATEGORIA)
    assert sum(1 for t in tarjetas if t["vendedor"] is None) > 0


def test_obtener_url_siguiente(html_pi_listado):
    assert obtener_url_siguiente(html_pi_listado) == (
        "https://www.portalinmobiliario.com/venta/casa/propiedades-usadas/"
        "_Desde_49_NoIndex_True"
    )


def test_obtener_url_siguiente_ultima_pagina():
    estado = {"pagination": {"next_page": {"url": None, "show": False}}}
    assert obtener_url_siguiente(_html_con_estado(estado)) is None


def test_obtener_url_siguiente_oculta():
    """next_page con show: false (límite de resultados) no devuelve URL."""
    estado = {
        "pagination": {"next_page": {"url": "https://x/_Desde_2001", "show": False}}
    }
    assert obtener_url_siguiente(_html_con_estado(estado)) is None


def test_parsear_total_resultados(html_pi_listado):
    assert parsear_total_resultados(html_pi_listado) == 63235


# ---------- Casos sintéticos ----------


def test_parsear_tarjetas_filtra_proyectos():
    estado = {
        "results": [
            _polycard(adid="MLC1"),
            _polycard(adid="MLC2", dominio="MLC-DEVELOPMENT_HOUSES_FOR_SALE"),
            {"id": "FACETED_SEARCH_INTERVENTION", "intervention": {}},
        ]
    }
    tarjetas = parsear_tarjetas(_html_con_estado(estado), CATEGORIA)
    assert [t["adid"] for t in tarjetas] == ["MLC1"]


def test_parsear_tarjetas_descuento():
    """previous_price 83 -> current_price 72 => bajó 13.3%."""
    estado = {"results": [_polycard(precio=72, previo=83)]}
    tarjeta = parsear_tarjetas(_html_con_estado(estado), CATEGORIA)[0]
    assert tarjeta["precio_valor"] == 72.0
    assert tarjeta["descuento_pct"] == 13.3


def test_parsear_tarjetas_m2_totales_del_listado():
    """'1.200 m² totales' va a m2_totales y no contamina m2_tarjeta."""
    estado = {
        "results": [_polycard(textos=["4 dormitorios", "3 baños", "1.200 m² totales"])]
    }
    tarjeta = parsear_tarjetas(_html_con_estado(estado), CATEGORIA)[0]
    assert tarjeta["m2_tarjeta"] is None
    assert tarjeta["m2_totales"] == 1200.0


def test_parsear_tarjetas_precio_desde_signal():
    """Sin componente price (tarjeta sin precio visible) cae a signal."""
    polycard = _polycard(precio=61, moneda="CLF")
    polycard["polycard"]["components"] = [
        c for c in polycard["polycard"]["components"] if c["type"] != "price"
    ]
    estado = {"results": [polycard]}
    tarjeta = parsear_tarjetas(_html_con_estado(estado), CATEGORIA)[0]
    assert tarjeta["precio_valor"] == 61.0
    assert tarjeta["precio_moneda"] == "UF"


def test_parsear_tarjetas_comuna_ultimo_segmento():
    """location.text es sucia: la comuna es el último segmento por coma."""
    estado = {
        "results": [_polycard(ubicacion="Sta. Elena 1 - 300, Colina, Chicureo, Colina")]
    }
    tarjeta = parsear_tarjetas(_html_con_estado(estado), CATEGORIA)[0]
    assert tarjeta["comuna"] == "Colina"


def test_parsear_tarjetas_sin_resultados():
    assert parsear_tarjetas("<html></html>", CATEGORIA) == []
