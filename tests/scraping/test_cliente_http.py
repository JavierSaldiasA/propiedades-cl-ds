"""Tests de src/scraping/cliente_http.py con transporte simulado (sin red)."""

import httpx
import pytest

from src.scraping.cliente_http import (
    ESPERA_BACKOFF_BASE,
    ErrorBloqueo,
    descargar,
    descargar_aviso,
)


def _cliente(status: int, cuerpo: str = "contenido") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=cuerpo)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_descargar_devuelve_texto():
    with _cliente(200) as cliente:
        assert descargar("https://ejemplo.cl/x", cliente) == "contenido"


def test_descargar_403_lanza_bloqueo():
    with _cliente(403) as cliente:
        with pytest.raises(ErrorBloqueo):
            descargar("https://ejemplo.cl/x", cliente)


def test_descargar_404_lanza_status_error():
    """descargar() estricta: un 4xx sube para quien no lo tolere."""
    with _cliente(404) as cliente:
        with pytest.raises(httpx.HTTPStatusError):
            descargar("https://ejemplo.cl/x", cliente)


def test_descargar_aviso_404_devuelve_none(monkeypatch):
    """Aviso dado de baja entre listado y detalle: None, sin abortar."""
    monkeypatch.setattr("src.scraping.cliente_http.time.sleep", lambda segundos: None)
    with _cliente(404) as cliente:
        assert descargar_aviso("https://ejemplo.cl/aviso", cliente) is None


def test_descargar_aviso_ok_devuelve_texto():
    with _cliente(200) as cliente:
        assert descargar_aviso("https://ejemplo.cl/aviso", cliente) == "contenido"


def test_descargar_aviso_propaga_bloqueo():
    """El 403 sigue siendo bloqueo: se propaga para abortar la corrida."""
    with _cliente(403) as cliente:
        with pytest.raises(ErrorBloqueo):
            descargar_aviso("https://ejemplo.cl/aviso", cliente)


def test_descargar_reintenta_y_agota_5xx(monkeypatch):
    """500 en todos los intentos: backoff simulado y ErrorBloqueo final."""
    llamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        llamadas["n"] += 1
        return httpx.Response(500)

    esperas: list[float] = []
    monkeypatch.setattr(
        "src.scraping.cliente_http.time.sleep", lambda s: esperas.append(s)
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(ErrorBloqueo):
            descargar("https://ejemplo.cl/x", cliente)

    assert llamadas["n"] == 3  # MAX_REINTENTOS
    assert esperas == [
        ESPERA_BACKOFF_BASE * 2**i for i in range(2)
    ]  # backoff exponencial entre reintentos
