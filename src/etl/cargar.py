"""CLI del ETL: parquet crudo de scraping -> tabla properties en Supabase.

Uso:
    python -m src.etl.cargar                       # última corrida de cada fuente
    python -m src.etl.cargar --fuente yapo         # solo una fuente
    python -m src.etl.cargar --fuente yapo --run-id 20260807_104024
    python -m src.etl.cargar --crear-schema        # aplica schema.sql
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import psycopg

from src.config import obtener_configuraciones
from src.etl.esquema import RUTA_SCHEMA, generar_schema
from src.etl.limpieza import transformar
from src.etl.uf import obtener_serie_uf
from src.etl.upsert import cargar_properties

logger = logging.getLogger(__name__)

# Fuente -> directorio del parquet crudo (los scrapers escriben las
# mismas columnas, así que el ETL es idéntico para todos).
DIRECTORIOS_RAW = {
    "yapo": Path("data/raw/yapo"),
    "portal_inmobiliario": Path("data/raw/portal_inmobiliario"),
    "toctoc": Path("data/raw/toctoc"),
}


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="src.etl.cargar",
        description="ETL: parquet crudo de scraping -> tabla properties en Supabase.",
    )
    parser.add_argument(
        "--fuente",
        choices=sorted(DIRECTORIOS_RAW),
        default=None,
        help=(
            "Cargar solo esta fuente (default: la última corrida de cada "
            "fuente disponible)."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Corrida de data/raw/<fuente>/ a procesar (default: la más reciente). "
        "Requiere --fuente.",
    )
    parser.add_argument(
        "--crear-schema",
        action="store_true",
        help="Aplica docker/db/schema.sql antes de cargar (idempotente).",
    )
    return parser.parse_args(argv)


def _ultimo_run_id(directorio_raw: Path) -> str | None:
    """Corrida más reciente de una fuente, o None si no hay corridas."""
    corridas = sorted(
        d.name
        for d in directorio_raw.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    return corridas[-1] if corridas else None


def _aplicar_schema(url_database: str) -> None:
    sql = generar_schema()
    with psycopg.connect(url_database) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql)
    logger.info("Schema aplicado desde la spec (%s)", RUTA_SCHEMA)


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


def _resolver_parquets(
    fuentes: list[str], run_id: str | None
) -> list[tuple[str, pd.DataFrame]]:
    """Fase 1 (disco): [(fuente, df)] de los parquets a procesar.

    Con --run-id explícito, un parquet inexistente aborta (el usuario pidió
    esa corrida específica); sin él se toma la más reciente de cada fuente,
    omitiendo con warning las fuentes sin corridas.
    """
    leidos: list[tuple[str, pd.DataFrame]] = []
    for fuente in fuentes:
        directorio_raw = DIRECTORIOS_RAW[fuente]
        if run_id is None:
            corrida = _ultimo_run_id(directorio_raw)
            if corrida is None:
                logger.warning(
                    "Sin corridas en %s/; se omite la fuente", directorio_raw
                )
                continue
        else:
            corrida = run_id
        ruta_parquet = directorio_raw / corrida / "propiedades.parquet"
        if not ruta_parquet.exists():
            raise SystemExit(f"No existe el parquet: {ruta_parquet}")
        logger.info("Fuente %s: leyendo corrida %s (%s)", fuente, corrida, ruta_parquet)
        df = pd.read_parquet(ruta_parquet)
        logger.info("Filas leídas del parquet: %d", len(df))
        leidos.append((fuente, df))
    if not leidos:
        raise SystemExit("No hay corridas disponibles de ninguna fuente.")
    return leidos


def _descargar_serie_uf(parquets: list[tuple[str, pd.DataFrame]]) -> pd.Series:
    """Fase 2 (red): serie UF única para el rango de fechas de todos los
    parquets, para no llamar a la API del BCCH una vez por fuente."""
    fechas = pd.concat(
        [df["fecha_publicacion"].fillna(df["fecha_scraping"]) for _, df in parquets]
    )
    logger.info(
        "Descargando serie UF (%s -> %s)", fechas.min().date(), fechas.max().date()
    )
    serie_uf = obtener_serie_uf(fechas.min().date(), fechas.max().date())
    logger.info("Serie UF: %d días", len(serie_uf))
    return serie_uf


def _procesar_fuente(
    df: pd.DataFrame, fuente: str, serie_uf: pd.Series, url_database: str
) -> None:
    """Fase 3 (BD): cadena del ETL + upsert para una fuente."""
    df = transformar(df, fuente, serie_uf)
    logger.info("Fuente %s: %d filas listas para carga", fuente, len(df))
    cargar_properties(df, url_database)


def main(argv: list[str] | None = None) -> None:
    args = parsear_argumentos(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.run_id and not args.fuente:
        raise SystemExit("--run-id requiere --fuente (los run-id son por fuente).")

    fuentes = [args.fuente] if args.fuente else sorted(DIRECTORIOS_RAW)
    parquets = _resolver_parquets(fuentes, args.run_id)

    config = obtener_configuraciones()
    if args.crear_schema:
        _aplicar_schema(config.url_database)
    _verificar_tabla(config.url_database)

    serie_uf = _descargar_serie_uf(parquets)
    for fuente, df in parquets:
        _procesar_fuente(df, fuente, serie_uf, config.url_database)
    logger.info("ETL terminado.")


if __name__ == "__main__":
    main()
