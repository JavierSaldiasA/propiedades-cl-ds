"""Cliente HTTP para el scraping cortés de Yapo.

Yapo sirve el contenido server-rendered, por lo que basta httpx con delays.
Playwright queda como fallback si aparece anti-bot a escala.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

MAX_REINTENTOS = 3
ESPERA_BACKOFF_BASE = 5.0  # segundos


class ErrorBloqueo(Exception):
    """Bloqueo anti-bot detectado (HTTP 403 o reintentos agotados)."""


def crear_cliente() -> httpx.Client:
    """Cliente con headers de navegador realista."""
    return httpx.Client(
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-CL,es;q=0.9",
        },
        follow_redirects=True,
        timeout=30.0,
    )


def esperar(delay: float) -> None:
    """Delay cortés con jitter uniforme entre `delay` y `2 * delay` segundos."""
    time.sleep(random.uniform(delay, delay * 2))


def _espera_backoff(intento: int) -> float:
    """Backoff exponencial para el reintento `intento` (1-index)."""
    return ESPERA_BACKOFF_BASE * (2 ** (intento - 1))


def reintentar_http(url: str, realizar: Callable[[], httpx.Response]) -> httpx.Response:
    """Ejecuta `realizar` (GET o POST) con reintentos y backoff exponencial.

    - HTTP 403 -> ErrorBloqueo (anti-bot, no se reintenta).
    - HTTP 429/5xx -> se reintenta; si se agotan -> ErrorBloqueo.
    - Errores de red (httpx.HTTPError) -> se reintentan; si persisten, se
      relanza la excepción original (no es un bloqueo anti-bot).

    Devuelve la respuesta; el llamante decide (raise_for_status, .json()...).
    """
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            respuesta = realizar()
        except httpx.HTTPError as error:
            logger.warning("Error de red en %s (intento %d): %s", url, intento, error)
            if intento == MAX_REINTENTOS:
                raise
            time.sleep(_espera_backoff(intento))
            continue
        if respuesta.status_code == 403:
            raise ErrorBloqueo(f"Bloqueo anti-bot en {url} (HTTP 403)")
        if respuesta.status_code in (429, 500, 502, 503):
            if intento == MAX_REINTENTOS:
                break  # sin éxito: no esperar para rendirse
            espera = _espera_backoff(intento)
            logger.warning(
                "HTTP %d en %s; reintento %d en %.0fs",
                respuesta.status_code,
                url,
                intento,
                espera,
            )
            time.sleep(espera)
            continue
        return respuesta
    raise ErrorBloqueo(f"Sin éxito tras {MAX_REINTENTOS} reintentos en {url}")


def descargar(url: str, cliente: httpx.Client) -> str:
    """Descarga una URL y devuelve el HTML como texto.

    Reintenta con backoff exponencial ante 429/5xx y errores de red
    (reintentar_http). Lanza ErrorBloqueo ante 403 o si se agotan los
    reintentos por HTTP 429/5xx.
    """
    respuesta = reintentar_http(url, lambda: cliente.get(url))
    respuesta.raise_for_status()
    return respuesta.text


def descargar_aviso(url: str, cliente: httpx.Client) -> str | None:
    """Descarga una página de detalle; None si ya no existe (HTTP 4xx).

    Los avisos pueden darse de baja entre que se scrapeó el listado y la
    visita de su detalle: es esperable y no debe abortar la corrida. Los
    bloqueos (ErrorBloqueo) sí se propagan.
    """
    try:
        return descargar(url, cliente)
    except httpx.HTTPStatusError as error:
        logger.warning(
            "Aviso no disponible (HTTP %d): %s",
            error.response.status_code,
            url,
        )
        return None
