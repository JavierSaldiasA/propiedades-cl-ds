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
    base.agregar_argumentos_comunes(parser, categorias=list(CATEGORIAS_PRINCIPALES))
    return parser.parse_args(argv)


class ScraperYapo(base.ScraperBase):
    nombre = "yapo"
    directorio_raw = base.RAIZ_PROYECTO / "data" / "raw" / "yapo"

    def parsear_detalle(self, html: str) -> dict:
        return parsear_detalle(html)

    def _leer_listado(self, ruta: Path) -> list[dict]:
        return parsear_tarjetas(base.leer_gzip(ruta), base.slug_desde_ruta(ruta))

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


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    base.configurar_logging()
    ScraperYapo().main(args)


if __name__ == "__main__":
    main()
