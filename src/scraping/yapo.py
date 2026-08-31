"""Scraper de Yapo Propiedades (ejecución manual/local).

Uso:
    python -m src.scraping.yapo --max-paginas 2 --max-detalles 10
    python -m src.scraping.yapo --reparsear 20260807_104024

Recorre los listados de las categorías indicadas, extrae las tarjetas,
visita las páginas de detalle (hasta --max-detalles) y guarda en
data/raw/yapo/<run_id>/ el HTML crudo comprimido (html/*.gz) más un
parquet con los campos tal como se scrapearon (sin normalizar; eso es
trabajo del ETL).

Con --reparsear se regenera el parquet de una corrida anterior desde sus
snapshots guardados, sin tocar la red.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.scraping import base
from src.scraping.yapo_detalle import parsear_detalle
from src.scraping.yapo_listado import (
    BASE_URL,
    CATEGORIAS_PRINCIPALES,
    obtener_url_siguiente,
    parsear_tarjetas,
    parsear_total_resultados,
)


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="src.scraping.yapo",
        description="Scraper de Yapo Propiedades (manual/local).",
    )
    parser.add_argument(
        "--categorias",
        nargs="+",
        default=list(CATEGORIAS_PRINCIPALES),
        metavar="SLUG",
        help="Slugs de categoría a scrapear (default: las 4 principales).",
    )
    parser.add_argument(
        "--max-paginas",
        type=int,
        default=5,
        help="Máximo de páginas de listado por categoría (default: 5).",
    )
    parser.add_argument(
        "--max-detalles",
        type=int,
        default=100,
        help="Máximo de páginas de detalle por corrida; 0 las omite (default: 100).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay base en segundos entre requests (default: 2.0).",
    )
    parser.add_argument(
        "--reparsear",
        metavar="RUN_ID",
        default=None,
        help=(
            "Regenera el parquet desde los snapshots guardados de esa corrida "
            "(sin red) y lo escribe en un run_id nuevo; omite el scraping."
        ),
    )
    return parser.parse_args(argv)


class ScraperYapo(base.ScraperBase):
    nombre = "yapo"
    directorio_raw = Path("data/raw/yapo")

    def parsear_detalle(self, html: str) -> dict:
        return parsear_detalle(html)

    def _leer_listado(self, ruta: Path) -> list[dict]:
        return parsear_tarjetas(base.leer_gzip(ruta), _slug_desde_ruta(ruta))

    def _scrapear_listados(self, args, cliente, directorio_html, registros) -> None:
        self._scrapear_listados_por_url(
            args,
            cliente,
            directorio_html,
            registros,
            construir_url=lambda categoria: f"{BASE_URL}/{categoria}",
            parsear_tarjetas=parsear_tarjetas,
            obtener_url_siguiente=obtener_url_siguiente,
            parsear_total=parsear_total_resultados,
        )


def _slug_desde_ruta(ruta: Path) -> str:
    """'listado_<categoria>_p1.html.gz' -> '<categoria>'."""
    nombre = Path(ruta.stem).stem  # quita .gz, .html
    return nombre.replace("listado_", "").split("_p")[0]


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ScraperYapo().main(args)


if __name__ == "__main__":
    main()
