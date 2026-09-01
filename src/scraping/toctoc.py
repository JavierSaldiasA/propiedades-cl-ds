"""Scraper de TOCTOC (ejecución manual/local).

Uso:
    python -m src.scraping.toctoc --max-paginas 2 --max-detalles 10
    python -m src.scraping.toctoc --reparsear 20260825_182426

A diferencia de Yapo (HTML) y Portal Inmobiliario (JSON NORDIC), TOCTOC
es una SPA cuyo buscador vive en un API interna: el scraper obtiene un
token de sesión, pagina el API de búsqueda (solo propiedades usadas) y
descarga la ficha server-rendered de cada aviso. Guarda en
data/raw/toctoc/<run_id>/ las respuestas crudas comprimidas (html/*.gz:
JSON del listado + HTML de las fichas) más un parquet con los campos tal
como se scrapearon (sin normalizar; eso es trabajo del ETL). Las columnas
son las mismas que las de los otros scrapers para reutilizar el ETL.

Con --reparsear se regenera el parquet de una corrida anterior desde sus
snapshots guardados, sin tocar la red (útil cuando el parser gana campos
nuevos).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date
from pathlib import Path

import httpx

from src.scraping import base
from src.scraping.toctoc_api import ErrorToken, buscar, obtener_token
from src.scraping.toctoc_ficha import parsear_ficha
from src.scraping.toctoc_listado import (
    CATEGORIAS_PRINCIPALES,
    hay_siguiente_pagina,
    obtener_pagina,
    parsear_listado,
    parsear_total,
)

logger = logging.getLogger(__name__)


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="src.scraping.toctoc",
        description="Scraper de TOCTOC (manual/local).",
    )
    base.agregar_argumentos_comunes(
        parser,
        categorias=list(CATEGORIAS_PRINCIPALES.values()),
        help_max_paginas="Máximo de páginas del buscador por operación (default: 5).",
    )
    return parser.parse_args(argv)


def _operaciones_necesarias(categorias: list[str]) -> list[str]:
    """Operaciones del API a descargar para cubrir las categorías pedidas."""
    operaciones = {
        operacion
        for (operacion, _), slug in CATEGORIAS_PRINCIPALES.items()
        if slug in categorias
    }
    if not operaciones:
        raise SystemExit(f"Categorías desconocidas: {categorias}")
    return sorted(operaciones)


class ScraperToctoc(base.ScraperBase):
    nombre = "toctoc"
    directorio_raw = base.RAIZ_PROYECTO / "data" / "raw" / "toctoc"
    proteger_url_en_ficha = True
    patron_listado = "listado_*.json.gz"
    # ErrorToken se usa solo para la obtención del token (no enmascara errores
    # de parsers, a diferencia de un ValueError genérico).
    clases_aborto = (base.ErrorBloqueo, KeyboardInterrupt, ErrorToken)

    def _preparar(self, args, cliente):
        self.token = obtener_token(cliente)
        logger.info("Token de sesión obtenido")

    def parsear_detalle(self, html: str) -> dict:
        return parsear_ficha(html)

    def _leer_listado(self, ruta: Path) -> list[dict]:
        return parsear_listado(json.loads(base.leer_gzip(ruta)))

    def _scrapear_listados(self, args, cliente, directorio_html, registros) -> None:
        categorias = set(args.categorias)
        for operacion in _operaciones_necesarias(args.categorias):
            pagina = 0
            while pagina < args.max_paginas:
                pagina += 1
                logger.info("Buscador %s página %d", operacion, pagina)
                try:
                    respuesta = buscar(cliente, self.token, operacion, pagina)
                except httpx.HTTPError as error:
                    if isinstance(error, httpx.HTTPStatusError):
                        logger.error(
                            "Búsqueda no disponible (HTTP %d); "
                            "se pasa a la siguiente operación",
                            error.response.status_code,
                        )
                    else:
                        logger.warning(
                            "Error de red en la búsqueda %s página %d (%s); "
                            "se omite la operación",
                            operacion,
                            pagina,
                            error,
                        )
                    break
                base.guardar_gzip(
                    directorio_html / f"listado_{operacion}_p{pagina}.json.gz",
                    json.dumps(respuesta, ensure_ascii=False),
                )
                if pagina == 1:
                    logger.info(
                        "  Total de avisos usados en la operación: %s",
                        parsear_total(respuesta),
                    )
                try:
                    avisos = parsear_listado(respuesta)
                except Exception:
                    logger.exception("  Error parseando la página %d; se omite", pagina)
                    break
                nuevos = 0
                for aviso in avisos:
                    if aviso["categoria_slug"] not in categorias:
                        continue
                    aviso["fecha_scraping"] = date.today()
                    if aviso["adid"] not in registros:
                        registros[aviso["adid"]] = aviso
                        nuevos += 1
                logger.info(
                    "  %d avisos extraídos (%d nuevos para las categorías pedidas)",
                    len(avisos),
                    nuevos,
                )
                if obtener_pagina(respuesta) != pagina:
                    logger.warning(
                        "  El API devolvió la página %d", obtener_pagina(respuesta)
                    )
                    break
                if not hay_siguiente_pagina(respuesta):
                    logger.info("  Última página de la operación")
                    break
                if pagina < args.max_paginas:
                    base.esperar(args.delay)


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    base.configurar_logging()
    ScraperToctoc().main(args)


if __name__ == "__main__":
    main()
