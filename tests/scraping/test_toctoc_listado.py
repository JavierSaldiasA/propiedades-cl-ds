"""Tests de src/scraping/toctoc_listado.py contra respuestas reales del API."""

import json

from src.scraping.toctoc_listado import (
    hay_siguiente_pagina,
    obtener_pagina,
    parsear_listado,
    parsear_total,
)


def _respuesta(texto: str) -> dict:
    return json.loads(texto)


def test_parsear_listado_venta_extrae_todos(json_toctoc_listado_venta):
    avisos = parsear_listado(_respuesta(json_toctoc_listado_venta))
    assert len(avisos) == 510
    assert len({a["adid"] for a in avisos}) == 510  # sin duplicados
    categorias = {a["categoria_slug"] for a in avisos}
    assert categorias == {"venta-casa", "venta-departamento"}


def test_parsear_listado_venta_primera(json_toctoc_listado_venta):
    aviso = parsear_listado(_respuesta(json_toctoc_listado_venta))[0]
    assert aviso["adid"] == "4231011"
    assert aviso["url_origen"] == (
        "https://www.toctoc.com/propiedades/compraparticularsr/departamento/"
        "santiago/departamento-libertad-1473-1522/4231011"
    )
    assert aviso["categoria_slug"] == "venta-departamento"
    assert aviso["tipo_operacion"] == "venta"
    assert aviso["tipo_propiedad"] == "departamento"
    assert aviso["titulo"] == "Departamento, Libertad 1473 1522"
    assert aviso["precio_texto"] == "UF 2.900"
    assert aviso["precio_valor"] == 2900.0
    assert aviso["precio_moneda"] == "UF"  # conversión [24] > [22] => UF
    assert aviso["comuna"] == "Santiago"
    assert aviso["region"] is None  # el listado no la trae
    assert aviso["latitud"] == -33.427746
    assert aviso["longitud"] == -70.67519
    assert str(aviso["fecha_publicacion"].date()) == "2026-06-25"


def test_parsear_listado_arriendo_precio_clp(json_toctoc_listado_arriendo):
    """Arriendo publicado en CLP: la conversión [24] (UF) < [22] => CLP."""
    avisos = parsear_listado(_respuesta(json_toctoc_listado_arriendo))
    assert len(avisos) == 510
    aviso = next(a for a in avisos if a["adid"] == "4309348")
    assert aviso["tipo_operacion"] == "arriendo"
    assert aviso["precio_valor"] == 470000.0
    assert aviso["precio_moneda"] == "CLP"
    assert aviso["precio_texto"] == "$ 470.000"
    assert aviso["comuna"] == "Ñuñoa"


def test_parsear_listado_arriendo_precio_uf(json_toctoc_listado_arriendo):
    """Arriendo publicado en UF: conversión [24] (CLP) > [22] (UF)."""
    avisos = parsear_listado(_respuesta(json_toctoc_listado_arriendo))
    en_uf = [a for a in avisos if a["precio_moneda"] == "UF"]
    en_clp = [a for a in avisos if a["precio_moneda"] == "CLP"]
    assert en_uf  # hay arriendos listados en UF (mayoría CLP)
    assert len(en_uf) < len(en_clp)
    # magnitudes plausibles (arriendos de lujo llegan a ~1.000 UF)
    assert all(0 < a["precio_valor"] < 4000 for a in en_uf)


def test_parsear_total_y_paginacion(json_toctoc_listado_venta):
    respuesta = _respuesta(json_toctoc_listado_venta)
    assert parsear_total(respuesta) == 67164
    assert obtener_pagina(respuesta) == 1
    assert hay_siguiente_pagina(respuesta) is True


def test_hay_siguiente_pagina_ultima():
    respuesta = {"resultados": {"Total": 510, "Pagina": 1, "TotalPorPagina": 510}}
    assert hay_siguiente_pagina(respuesta) is False
    respuesta = {"resultados": {"Total": 100, "Pagina": 2, "TotalPorPagina": 510}}
    assert hay_siguiente_pagina(respuesta) is False


def test_parsear_listado_ignora_tipos_desconocidos():
    """URLs sin patrón conocido (otros tipos de propiedad) se omiten."""
    respuesta = {
        "resultados": {
            "Total": 1,
            "Pagina": 1,
            "TotalPorPagina": 510,
            "Propiedades": [
                [
                    0,
                    1,
                    0.0,
                    0.0,
                    0,
                    0,
                    0,
                    "X",
                    0,
                    0,
                    False,
                    False,
                    0,
                    False,
                    "",
                    0,
                    0,
                    0,
                    0,
                    0,
                    "",
                    0,
                    100.0,
                    100.0,
                    5000.0,
                    0.0,
                    None,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    False,
                    False,
                    False,
                    0,
                    "Oficina X",
                    "https://www.toctoc.com/propiedades/compra/oficina/santiago/x/1",
                    0,
                    0,
                    0,
                    "",
                ]
            ],
        }
    }
    assert parsear_listado(respuesta) == []


def test_parsear_listado_respuesta_vacia():
    assert parsear_listado({}) == []
    assert parsear_total({}) is None
    assert hay_siguiente_pagina({}) is False
