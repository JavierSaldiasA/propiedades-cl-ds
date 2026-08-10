"""Limpieza y normalización del parquet crudo de scraping.

Funciones puras: reciben DataFrame y devuelven DataFrame, sin tocar red,
BD ni disco.
"""

from __future__ import annotations

import logging

import pandas as pd

from src.etl.uf import convertir_a_clp

logger = logging.getLogger(__name__)

FUENTE_YAPO = "yapo"

# Columnas de la tabla properties (docker/db/schema.sql), en orden, sin `id`
COLUMNAS_PROPERTIES = [
    "fuente",
    "url_origen",
    "tipo_operacion",
    "tipo_propiedad",
    "precio_valor",
    "precio_moneda",
    "precio_clp_normalizado",
    "m2_util",
    "m2_total",
    "dormitorios",
    "banos",
    "estacionamientos",
    "bodega",
    "comuna",
    "region",
    "antiguedad_anios",
    "descripcion",
    "fecha_publicacion",
    "fecha_scraping",
]


def normalizar_precios(df: pd.DataFrame, serie_uf: pd.Series) -> pd.DataFrame:
    """Agrega `precio_clp_normalizado` (UF→CLP con la UF de la publicación).

    Si el aviso no tiene fecha de publicación se usa la fecha de scraping.
    """
    df = df.copy()
    fechas = df["fecha_publicacion"].fillna(df["fecha_scraping"])
    df["precio_clp_normalizado"] = pd.array(
        [
            convertir_a_clp(valor, moneda, fecha, serie_uf)
            for valor, moneda, fecha in zip(
                df["precio_valor"], df["precio_moneda"], fechas
            )
        ],
        dtype="Float64",
    )
    return df


def normalizar_m2(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback en cadena por inconsistencia de las fuentes (supuesto del MVP):

    - m2_util  := m2_construida (detalle) -> m2_tarjeta
    - m2_total := m2_totales (detalle) -> m2_construida -> m2_tarjeta
    """
    df = df.copy()
    df["m2_util"] = df["m2_construida"].fillna(df["m2_tarjeta"])
    df["m2_total"] = (
        df["m2_totales"].fillna(df["m2_construida"]).fillna(df["m2_tarjeta"])
    )
    return df


def calcular_antiguedad(df: pd.DataFrame) -> pd.DataFrame:
    """antiguedad_anios := año(fecha_scraping) - anio_construccion (mínimo 0)."""
    df = df.copy()
    antiguedad = df["fecha_scraping"].dt.year - df["anio_construccion"]
    df["antiguedad_anios"] = antiguedad.clip(lower=0).astype("Int64")
    return df


def preparar_para_carga(df: pd.DataFrame, fuente: str = FUENTE_YAPO) -> pd.DataFrame:
    """Deja el DataFrame listo para la tabla properties.

    Agrega `fuente`, descarta filas sin url_origen, deduplica por
    (fuente, url_origen) conservando la última versión y selecciona las
    columnas del schema en orden.
    """
    df = df.copy()
    df["fuente"] = fuente

    sin_url = df["url_origen"].isna().sum()
    if sin_url:
        logger.warning("Se descartan %d filas sin url_origen", sin_url)
        df = df.dropna(subset=["url_origen"])

    duplicados = df.duplicated(subset=["fuente", "url_origen"]).sum()
    if duplicados:
        logger.warning("Se deduplican %d filas por (fuente, url_origen)", duplicados)
        df = df.drop_duplicates(subset=["fuente", "url_origen"], keep="last")

    return df[COLUMNAS_PROPERTIES].reset_index(drop=True)
