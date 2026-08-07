"""Cliente HTTP para el scraping cortés de Yapo.

Yapo sirve el contenido server-rendered, por lo que basta httpx con delays.
Playwright queda como fallback si aparece anti-bot a escala.
"""

from __future__ import annotations

import logging
import random
import time

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


def descargar(url: str, cliente: httpx.Client) -> str:
    """Descarga una URL y devuelve el HTML como texto.

    Reintenta con backoff exponencial ante 429/5xx y errores de red.
    Lanza ErrorBloqueo ante 403 o si se agotan los reintentos por HTTP 429/5xx.
    """
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            respuesta = cliente.get(url)
        except httpx.HTTPError as error:
            logger.warning("Error de red en %s (intento %d): %s", url, intento, error)
            if intento == MAX_REINTENTOS:
                raise
            time.sleep(ESPERA_BACKOFF_BASE * intento)
            continue
        if respuesta.status_code == 403:
            raise ErrorBloqueo(f"Bloqueo anti-bot en {url} (HTTP 403)")
        if respuesta.status_code in (429, 500, 502, 503):
            espera = ESPERA_BACKOFF_BASE * (2 ** (intento - 1))
            logger.warning(
                "HTTP %d en %s; reintento %d en %.0fs",
                respuesta.status_code,
                url,
                intento,
                espera,
            )
            time.sleep(espera)
            continue
        respuesta.raise_for_status()
        return respuesta.text
    raise ErrorBloqueo(f"Sin éxito tras {MAX_REINTENTOS} reintentos en {url}")
