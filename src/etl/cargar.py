"""CLI del ETL: parquet crudo de scraping -> tabla properties en Supabase.

Uso:
    python -m src.etl.cargar                      # última corrida disponible
    python -m src.etl.cargar --run-id 20260807_104024
    python -m src.etl.cargar --crear-schema       # aplica schema.sql y carga
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import psycopg

from src.config import obtener_configuraciones
from src.etl.carga import cargar_properties
from src.etl.limpieza import (
    calcular_antiguedad,
    normalizar_m2,
    normalizar_precios,
    preparar_para_carga,
)
from src.etl.uf import obtener_serie_uf

logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path("data/raw/yapo")
RUTA_SCHEMA = Path("docker/db/schema.sql")


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="src.etl.cargar",
        description="ETL: parquet crudo de Yapo -> tabla properties en Supabase.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Corrida de data/raw/yapo/ a procesar (default: la más reciente).",
    )
    parser.add_argument(
        "--crear-schema",
        action="store_true",
        help="Aplica docker/db/schema.sql antes de cargar (idempotente).",
    )
    return parser.parse_args(argv)


def _ultimo_run_id() -> str:
    corridas = sorted(
        d.name
        for d in DIRECTORIO_RAW.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not corridas:
        raise SystemExit(f"No hay corridas en {DIRECTORIO_RAW}/")
    return corridas[-1]


def _aplicar_schema(url_database: str) -> None:
    sql = RUTA_SCHEMA.read_text(encoding="utf-8")
    with psycopg.connect(url_database) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql)
    logger.info("Schema aplicado desde %s", RUTA_SCHEMA)


def _verificar_tabla(url_database: str) -> None:
    with psycopg.connect(url_database) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.properties')")
            existe = cursor.fetchone()[0] is not None
    if not existe:
        raise SystemExit(
            "La tabla properties no existe. Ejecuta primero: "
            "python -m src.etl.cargar --crear-schema"
        )


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    run_id = args.run_id or _ultimo_run_id()
    ruta_parquet = DIRECTORIO_RAW / run_id / "propiedades.parquet"
    if not ruta_parquet.exists():
        raise SystemExit(f"No existe el parquet: {ruta_parquet}")
    logger.info("Procesando corrida %s (%s)", run_id, ruta_parquet)

    config = obtener_configuraciones()
    if args.crear_schema:
        _aplicar_schema(config.url_database)
    _verificar_tabla(config.url_database)

    df = pd.read_parquet(ruta_parquet)
    logger.info("Filas leídas del parquet: %d", len(df))

    fechas = df["fecha_publicacion"].fillna(df["fecha_scraping"])
    logger.info(
        "Descargando serie UF (%s -> %s)", fechas.min().date(), fechas.max().date()
    )
    serie_uf = obtener_serie_uf(fechas.min().date(), fechas.max().date())
    logger.info("Serie UF: %d días", len(serie_uf))

    df = normalizar_precios(df, serie_uf)
    df = normalizar_m2(df)
    df = calcular_antiguedad(df)
    df = preparar_para_carga(df)
    logger.info("Filas listas para carga: %d", len(df))

    cargar_properties(df, config.url_database)
    logger.info("ETL terminado.")


if __name__ == "__main__":
    main()
