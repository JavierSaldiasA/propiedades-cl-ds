"""Carga del DataFrame normalizado a la tabla properties (Supabase Postgres).

Upsert por (fuente, url_origen): si el aviso ya existe se actualizan sus
columnas (precio, fechas, etc.) con la versión más reciente scrapeada.
"""

from __future__ import annotations

import logging

import pandas as pd
import psycopg

logger = logging.getLogger(__name__)

COLUMNAS_CONFLICTO = ("fuente", "url_origen")


def _valor_nativo(valor):
    """pd.NA/NaN -> None; Timestamp -> date; escalares numpy -> nativos Python.

    psycopg no sabe adaptar pd.NA ni tipos numpy: hay que convertirlos.
    """
    if valor is None:
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if pd.isna(valor):
        return None
    if hasattr(valor, "item"):  # escalar numpy
        return valor.item()
    return valor


def _filas_nativas(df: pd.DataFrame) -> list[tuple]:
    """Filas como tuplas de valores nativos, en el orden de df.columns."""
    return [
        tuple(_valor_nativo(v) for v in fila)
        for fila in df.itertuples(index=False, name=None)
    ]


def _sql_upsert(columnas: list[str]) -> str:
    marcadores = ", ".join(["%s"] * len(columnas))
    asignaciones = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columnas if c not in COLUMNAS_CONFLICTO
    )
    return (
        f"INSERT INTO properties ({', '.join(columnas)}) VALUES ({marcadores}) "
        f"ON CONFLICT (fuente, url_origen) DO UPDATE SET {asignaciones}"
    )


def cargar_properties(df: pd.DataFrame, url_database: str) -> int:
    """Upsert del DataFrame en properties. Devuelve la cantidad de filas."""
    if df.empty:
        logger.warning("DataFrame vacío: no se carga nada.")
        return 0
    filas = _filas_nativas(df)
    sql = _sql_upsert(list(df.columns))
    with psycopg.connect(url_database) as conexion:
        with conexion.cursor() as cursor:
            cursor.executemany(sql, filas)
    logger.info("Upsert completado: %d filas en properties", len(filas))
    return len(filas)
