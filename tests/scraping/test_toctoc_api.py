"""Tests de src/scraping/toctoc_api.py con transporte simulado (sin red)."""

import json

import httpx
import pytest

from src.scraping.cliente_http import ErrorBloqueo
from src.scraping.toctoc_api import (
    OPERACIONES,
    ErrorToken,
    buscar,
    obtener_token,
)

PAGINA = (
    '<html><script id="react-engine-props" type="application/json">'
    '{"token": "jwt-de-prueba", "config": {}}'
    "</script></html>"
)


def _cliente_mock(pagina=PAGINA, respuesta_api=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/resultados"):
            return httpx.Response(200, text=pagina)
        if request.url.path == "/api/mapa/GetProps":
            assert request.headers["x-access-token"] == "jwt-de-prueba"
            return httpx.Response(200, json=respuesta_api or {})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_obtener_token():
    with _cliente_mock() as cliente:
        assert obtener_token(cliente) == "jwt-de-prueba"


def test_obtener_token_sin_script():
    with _cliente_mock(pagina="<html><body>Sin script</body></html>") as cliente:
        try:
            obtener_token(cliente)
        except ValueError as error:
            assert "react-engine-props" in str(error)
        else:
            raise AssertionError("debía fallar sin el script")


def test_buscar_envia_token_y_pagina():
    with _cliente_mock(respuesta_api={"resultados": {"Total": 10}}) as cliente:
        respuesta = buscar(cliente, "jwt-de-prueba", "venta", 3)
    assert respuesta["resultados"]["Total"] == 10


def test_buscar_cuerpo_por_operacion():
    cuerpos = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/mapa/GetProps":
            cuerpos.append(json.loads(request.content))
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as cliente:
        buscar(cliente, "t", "venta", 1)
        buscar(cliente, "t", "arriendo", 2)

    assert cuerpos[0]["operacion"] == OPERACIONES["venta"]
    assert cuerpos[0]["estado"] == 2  # solo usadas
    assert cuerpos[0]["pagina"] == 1
    assert cuerpos[1]["operacion"] == OPERACIONES["arriendo"]
    assert cuerpos[1]["pagina"] == 2


def test_obtener_token_malformado_lanza_error_token():
    pagina = (
        '<html><script id="react-engine-props" type="application/json">'
        "no-es-json"
        "</script></html>"
    )
    with _cliente_mock(pagina=pagina) as cliente:
        with pytest.raises(ErrorToken):
            obtener_token(cliente)


def test_buscar_403_lanza_bloqueo(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    monkeypatch.setattr("src.scraping.cliente_http.time.sleep", lambda segundos: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(ErrorBloqueo):
            buscar(cliente, "t", "venta", 1)


def test_buscar_agota_5xx_lanza_bloqueo(monkeypatch):
    llamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas["n"] += 1
        return httpx.Response(500)

    monkeypatch.setattr("src.scraping.cliente_http.time.sleep", lambda segundos: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(ErrorBloqueo):
            buscar(cliente, "t", "venta", 1)
    assert llamadas["n"] == 3


def test_buscar_error_de_red_relanza_y_reintenta(monkeypatch):
    llamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas["n"] += 1
        raise httpx.ConnectError("red caída")

    monkeypatch.setattr("src.scraping.cliente_http.time.sleep", lambda segundos: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(httpx.ConnectError):
            buscar(cliente, "t", "venta", 1)
    assert llamadas["n"] == 3
