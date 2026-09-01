"""Carga del DataFrame normalizado a la tabla properties (Supabase Postgres).

Upsert por (fuente, url_origen): si el aviso ya existe se actualizan sus
columnas (precio, fechas, etc.) con la versión más reciente scrapeada.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import psycopg

from src.etl.esquema import COLUMNAS_CONFLICTO

logger = logging.getLogger(__name__)


def _valor_nativo(valor: Any) -> Any:
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


def _valores_nativos_columna(serie: pd.Series) -> tuple:
    """Columna convertida a tupla de valores nativos en orden.

    Vectorizada por columna: las fechas se pasan a `date` con `.dt.date`
    (C-speed) y el resto con una sola difusión a objeto; `_valor_nativo`
    solo se aplica donde queda tipo numpy/pandas residual.
    """
    if pd.api.types.is_datetime64_any_dtype(serie.dtype):
        return tuple(None if pd.isna(v) else v for v in serie.dt.date.tolist())
    return tuple(_valor_nativo(v) for v in serie.to_numpy(dtype=object))


def _filas_nativas(df: pd.DataFrame) -> list[tuple]:
    """Filas como tuplas de valores nativos, en el orden de df.columns."""
    return list(zip(*(_valores_nativos_columna(df[col]) for col in df.columns)))


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
