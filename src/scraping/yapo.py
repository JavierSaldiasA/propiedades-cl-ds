"""Scraper de Yapo Propiedades (ejecución manual/local).

Uso:
    python -m src.scraping.yapo --max-paginas 2 --max-detalles 10

Recorre los listados de las categorías indicadas, extrae las tarjetas,
visita las páginas de detalle (hasta --max-detalles) y guarda en
data/raw/yapo/<run_id>/ el HTML crudo comprimido (html/*.gz) más un
parquet con los campos tal como se scrapearon (sin normalizar; eso es
trabajo del ETL).
"""

from __future__ import annotations

import argparse
import gzip
import logging
from datetime import date, datetime
from pathlib import Path

import httpx
import pandas as pd

from src.scraping.cliente_http import ErrorBloqueo, crear_cliente, descargar, esperar
from src.scraping.yapo_detalle import parsear_detalle
from src.scraping.yapo_listado import (
    BASE_URL,
    CATEGORIAS_PRINCIPALES,
    obtener_url_siguiente,
    parsear_tarjetas,
    parsear_total_resultados,
)

logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path("data/raw/yapo")

COLUMNAS = [
    "adid",
    "url_origen",
    "categoria_slug",
    "tipo_operacion",
    "tipo_propiedad",
    "titulo",
    "precio_texto",
    "precio_valor",
    "precio_moneda",
    "comuna",
    "region",
    "m2_tarjeta",
    "dormitorios",
    "banos",
    "estacionamientos",
    "vendedor",
    "es_profesional",
    "etiqueta",
    "descuento_pct",
    "descripcion",
    "fecha_publicacion",
    "m2_construida",
    "m2_totales",
    "gastos_comunes",
    "anio_construccion",
    "piso",
    "piscina",
    "bodega",
    "beneficios",
    "latitud",
    "longitud",
    "fecha_scraping",
]

COLUMNAS_ENTERAS = (
    "dormitorios",
    "banos",
    "estacionamientos",
    "anio_construccion",
    "piso",
)
COLUMNAS_FLOTANTES = (
    "precio_valor",
    "m2_tarjeta",
    "m2_construida",
    "m2_totales",
    "gastos_comunes",
    "descuento_pct",
    "latitud",
    "longitud",
)
COLUMNAS_BOOLEANAS = ("es_profesional", "piscina", "bodega")
COLUMNAS_FECHAS = ("fecha_publicacion", "fecha_scraping")


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
    return parser.parse_args(argv)


def _guardar_html(ruta: Path, html: str) -> None:
    with gzip.open(ruta, "wt", encoding="utf-8") as archivo:
        archivo.write(html)


def _a_dataframe(registros: dict[str, dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(registros.values())).reindex(columns=COLUMNAS)
    for columna in COLUMNAS_ENTERAS:
        df[columna] = df[columna].astype("Int64")
    for columna in COLUMNAS_FLOTANTES:
        df[columna] = df[columna].astype("Float64")
    for columna in COLUMNAS_BOOLEANAS:
        df[columna] = df[columna].astype("boolean")
    for columna in COLUMNAS_FECHAS:
        df[columna] = pd.to_datetime(df[columna])
    return df


def _escribir_parquet(registros: dict[str, dict], directorio: Path) -> None:
    if not registros:
        logger.warning("No hay registros; no se escribe parquet.")
        return
    ruta = directorio / "propiedades.parquet"
    _a_dataframe(registros).to_parquet(ruta, index=False)
    logger.info("Parquet escrito: %s (%d avisos)", ruta, len(registros))


def _scrapear_listados(args, cliente, directorio_html, registros) -> None:
    for categoria in args.categorias:
        url: str | None = f"{BASE_URL}/{categoria}"
        pagina = 0
        while url and pagina < args.max_paginas:
            pagina += 1
            logger.info("Listado %s página %d: %s", categoria, pagina, url)
            html = descargar(url, cliente)
            _guardar_html(
                directorio_html / f"listado_{categoria}_p{pagina}.html.gz", html
            )
            if pagina == 1:
                total = parsear_total_resultados(html)
                logger.info("  Total de avisos en la categoría: %s", total)
            try:
                tarjetas = parsear_tarjetas(html, categoria)
            except Exception:
                logger.exception("  Error parseando %s; se omite la página", url)
                break
            logger.info("  %d tarjetas extraídas", len(tarjetas))
            for tarjeta in tarjetas:
                tarjeta["fecha_scraping"] = date.today()
                registros.setdefault(tarjeta["adid"], tarjeta)
            url = obtener_url_siguiente(html)
            if url and pagina < args.max_paginas:
                esperar(args.delay)


def _scrapear_detalles(args, cliente, directorio_html, registros) -> None:
    candidatos = list(registros.values())[: args.max_detalles]
    for indice, registro in enumerate(candidatos, start=1):
        logger.info(
            "Detalle %d/%d: %s", indice, len(candidatos), registro["url_origen"]
        )
        html = descargar(registro["url_origen"], cliente)
        _guardar_html(directorio_html / f"detalle_{registro['adid']}.html.gz", html)
        try:
            detalle = parsear_detalle(html)
        except Exception:
            logger.exception(
                "  Error parseando detalle %s; se conserva la tarjeta",
                registro["adid"],
            )
            continue
        registro.update({k: v for k, v in detalle.items() if v is not None})
        if indice < len(candidatos):
            esperar(args.delay)


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    directorio_salida = DIRECTORIO_RAW / run_id
    directorio_html = directorio_salida / "html"
    directorio_html.mkdir(parents=True, exist_ok=True)
    logger.info("Directorio de salida: %s", directorio_salida)

    registros: dict[str, dict] = {}  # adid -> registro (dedup por adid)
    cliente = crear_cliente()
    try:
        _scrapear_listados(args, cliente, directorio_html, registros)
        if args.max_detalles > 0:
            _scrapear_detalles(args, cliente, directorio_html, registros)
    except (ErrorBloqueo, KeyboardInterrupt, httpx.HTTPError) as error:
        logger.error("Corrida abortada: %s", error)
    finally:
        cliente.close()
        _escribir_parquet(registros, directorio_salida)

    logger.info("Listo: %d avisos únicos en %s", len(registros), directorio_salida)


if __name__ == "__main__":
    main()
