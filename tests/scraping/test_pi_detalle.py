"""Tests de src/scraping/pi_detalle.py contra HTML real (ver fixtures/)."""

import json
from datetime import datetime

from src.scraping.pi_detalle import parsear_detalle


def test_parsear_detalle_casa(html_pi_detalle_casa):
    """VIP de una casa individual en venta (UF, Las Condes)."""
    detalle = parsear_detalle(html_pi_detalle_casa)
    assert detalle["precio_valor"] == 16950.0
    assert detalle["precio_moneda"] == "UF"  # CLF normalizado
    assert detalle["comuna"] == "Las Condes"
    assert detalle["region"] == "RM (Metropolitana)"
    assert detalle["dormitorios"] == 4
    assert detalle["banos"] == 4
    assert detalle["estacionamientos"] == 3
    assert detalle["m2_construida"] == 163.0
    assert detalle["m2_totales"] == 257.0
    assert detalle["gastos_comunes"] is None
    assert detalle["bodega"] is True  # "Bodegas: 1"
    assert detalle["anio_construccion"] == datetime.now().year - 54
    assert detalle["piso"] is None  # atributo de departamento
    assert detalle["piscina"] is False
    assert detalle["latitud"] == -33.3935729
    assert detalle["longitud"] == -70.5484109
    assert detalle["vendedor"] == "Entre Propiedades"
    assert "Casa remodelada" in detalle["descripcion"]
    assert "Jardín" in detalle["beneficios"]
    assert "Piscina" not in detalle["beneficios"]  # era "No"
    assert "fecha_publicacion" not in detalle  # PI no la expone


def test_parsear_detalle_departamento(html_pi_detalle_depto):
    """VIP de un departamento individual en arriendo (CLP, Independencia)."""
    detalle = parsear_detalle(html_pi_detalle_depto)
    assert detalle["precio_valor"] == 400000.0
    assert detalle["precio_moneda"] == "CLP"
    assert detalle["comuna"] == "Independencia"
    assert detalle["region"] == "RM (Metropolitana)"
    assert detalle["dormitorios"] == 2
    assert detalle["banos"] == 1
    assert detalle["estacionamientos"] == 0
    assert detalle["m2_construida"] == 36.0
    assert detalle["m2_totales"] == 37.54  # coma decimal es-CL
    assert detalle["gastos_comunes"] == 70000.0  # "70.000 CLP"
    assert detalle["bodega"] is False  # "Bodegas: 0"
    assert detalle["piso"] == 20
    assert detalle["anio_construccion"] == datetime.now().year - 9
    assert detalle["latitud"] == -33.4204203
    assert detalle["longitud"] == -70.6599348
    assert detalle["vendedor"] == "Msr Broker"
    assert "Ascensor" in detalle["beneficios"]


def test_parsear_detalle_precio_desde_jsonld():
    """Sin componente price, el precio cae al JSON-LD (schema Product)."""
    estado = {
        "schema": [
            {
                "@type": "Product",
                "name": "Casa",
                "offers": {"price": 3824, "priceCurrency": "CLF"},
            }
        ]
    }
    payload = {"appProps": {"pageProps": {"initialState": estado}}}
    html = (
        '<html><script id="__NORDIC_RENDERING_CTX__">'
        f"_n.ctx.r={json.dumps(payload)};"
        "_n.ctx.r.assets.manifest=new Map([]);</script></html>"
    )
    detalle = parsear_detalle(html)
    assert detalle["precio_valor"] == 3824.0
    assert detalle["precio_moneda"] == "UF"
    assert detalle["comuna"] is None
