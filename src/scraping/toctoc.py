"""Scraper de TOCTOC (ejecución manual/local).

Uso:
    python -m src.scraping.toctoc --max-paginas 2 --max-detalles 10

A diferencia de Yapo (HTML) y Portal Inmobiliario (JSON NORDIC), TOCTOC
es una SPA cuyo buscador vive en un API interna: el scraper obtiene un
token de sesión, pagina el API de búsqueda (solo propiedades usadas) y
descarga la ficha server-rendered de cada aviso. Guarda en
data/raw/toctoc/<run_id>/ las respuestas crudas comprimidas (html/*.gz:
JSON del listado + HTML de las fichas) más un parquet con los campos tal
como se scrapearon (sin normalizar; eso es trabajo del ETL). Las columnas
son las mismas que las de los otros scrapers para reutilizar el ETL.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
from datetime import date, datetime
from pathlib import Path

import httpx
import pandas as pd

from src.scraping.cliente_http import (
    ErrorBloqueo,
    crear_cliente,
    descargar_aviso,
    esperar,
)
from src.scraping.toctoc_api import buscar, obtener_token
from src.scraping.toctoc_ficha import parsear_ficha
from src.scraping.toctoc_listado import (
    CATEGORIAS_PRINCIPALES,
    hay_siguiente_pagina,
    obtener_pagina,
    parsear_listado,
    parsear_total,
)

logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path("data/raw/toctoc")

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
        prog="src.scraping.toctoc",
        description="Scraper de TOCTOC (manual/local).",
    )
    parser.add_argument(
        "--categorias",
        nargs="+",
        default=list(CATEGORIAS_PRINCIPALES.values()),
        metavar="SLUG",
        help="Slugs de categoría a scrapear (default: las 4 principales).",
    )
    parser.add_argument(
        "--max-paginas",
        type=int,
        default=5,
        help="Máximo de páginas del buscador por operación (default: 5).",
    )
    parser.add_argument(
        "--max-detalles",
        type=int,
        default=100,
        help="Máximo de fichas por corrida; 0 las omite (default: 100).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay base en segundos entre requests (default: 2.0).",
    )
    return parser.parse_args(argv)


def _guardar_gzip(ruta: Path, contenido: str) -> None:
    with gzip.open(ruta, "wt", encoding="utf-8") as archivo:
        archivo.write(contenido)


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


def _scrapear_listados(args, cliente, token, directorio_html, registros) -> None:
    """Pagina el buscador por operación y guarda los avisos de las categorías.

    El buscador mezcla casas y departamentos (no filtra por tipo): cada
    página se descarga una sola vez por operación y los avisos se reparten
    a su categoría según la URL.
    """
    categorias = set(args.categorias)
    for operacion in _operaciones_necesarias(args.categorias):
        pagina = 0
        while pagina < args.max_paginas:
            pagina += 1
            logger.info("Buscador %s página %d", operacion, pagina)
            try:
                respuesta = buscar(cliente, token, operacion, pagina)
            except httpx.HTTPStatusError as error:
                logger.error(
                    "Búsqueda no disponible (HTTP %d); "
                    "se pasa a la siguiente operación",
                    error.response.status_code,
                )
                break
            _guardar_gzip(
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
                esperar(args.delay)


def _scrapear_detalles(args, cliente, directorio_html, registros) -> None:
    candidatos = list(registros.values())[: args.max_detalles]
    for indice, registro in enumerate(candidatos, start=1):
        logger.info(
            "Detalle %d/%d: %s", indice, len(candidatos), registro["url_origen"]
        )
        html = descargar_aviso(registro["url_origen"], cliente)
        if html is None:  # aviso dado de baja entre listado y detalle
            continue
        _guardar_gzip(directorio_html / f"detalle_{registro['adid']}.html.gz", html)
        try:
            detalle = parsear_ficha(html)
        except Exception:
            logger.exception(
                "  Error parseando ficha %s; se conserva el listado",
                registro["adid"],
            )
            continue
        # url_origen no se sobrescribe: la ficha puede reportar una URL
        # canónica con hash distinta de la del listado, y la dedup de la
        # BD depende de una URL estable por aviso.
        registro.update(
            {k: v for k, v in detalle.items() if v is not None and k != "url_origen"}
        )
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
        token = obtener_token(cliente)
        logger.info("Token de sesión obtenido")
        _scrapear_listados(args, cliente, token, directorio_html, registros)
        if args.max_detalles > 0:
            _scrapear_detalles(args, cliente, directorio_html, registros)
    except (ErrorBloqueo, KeyboardInterrupt, httpx.HTTPError, ValueError) as error:
        logger.error("Corrida abortada: %s", error)
    finally:
        cliente.close()
        _escribir_parquet(registros, directorio_salida)

    logger.info("Listo: %d avisos únicos en %s", len(registros), directorio_salida)


if __name__ == "__main__":
    main()
