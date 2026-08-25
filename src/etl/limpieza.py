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

# Techo de plausibilidad de superficie (10 ha): por encima es casi seguro un
# error de dedo del anunciante (ej. "1.800.000 m² útiles" que quería ser
# 1.800; observado en Portal Inmobiliario, MLC4361365328). Además protege el
# NUMERIC(8,2) de la BD, que revienta con valores ≥ 10⁶.
M2_MAXIMO_PLAUSIBLE = 100_000

# Techos de plausibilidad de precio por moneda: por encima es casi seguro un
# error del anunciante (ej. un monto CLP tipeado con moneda UF: "UF125.000.000"
# ≈ 5×10¹² CLP; observado en Yapo, aviso 32850692). Con margen amplio sobre
# los legítimos observados (105.000 UF: terreno en Vitacura; 1.900M CLP) y
# blindan el NUMERIC(14,2) de la BD, que revienta con valores ≥ 10¹²
# (500.000 UF × UF del día ≈ 2×10¹⁰ < 10¹²).
PRECIOS_MAXIMOS_PLAUSIBLES = {"UF": 500_000, "CLP": 10_000_000_000}

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
    "gastos_comunes",
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


def _anular_precios_implausibles(df: pd.DataFrame) -> pd.DataFrame:
    """precio_valor > tope de su moneda -> NA (error de origen, no se corrige)."""
    sobre_umbral = pd.Series(False, index=df.index)
    for moneda, maximo in PRECIOS_MAXIMOS_PLAUSIBLES.items():
        es_moneda = df["precio_moneda"] == moneda
        excede = (es_moneda & (df["precio_valor"] > maximo)).fillna(False)
        sobre_umbral |= excede
    if sobre_umbral.any():
        logger.warning(
            "Se anulan %d precios por superar el tope de plausibilidad de su "
            "moneda (error de origen: ej. monto CLP tipeado como UF)",
            int(sobre_umbral.sum()),
        )
        df = df.copy()
        df.loc[sobre_umbral, "precio_valor"] = pd.NA
    return df


def normalizar_precios(df: pd.DataFrame, serie_uf: pd.Series) -> pd.DataFrame:
    """Agrega `precio_clp_normalizado` (UF→CLP con la UF de la publicación).

    Si el aviso no tiene fecha de publicación se usa la fecha de scraping.
    Los precios implausibles (sobre el tope de su moneda) se anulan antes
    de convertir: son errores del anunciante y desbordarían el
    NUMERIC(14,2) de la tabla.
    """
    df = _anular_precios_implausibles(df)
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


def _anular_implausibles(serie: pd.Series, columna: str) -> pd.Series:
    """m² > M2_MAXIMO_PLAUSIBLE -> NA (error de origen, no se corrige)."""
    implausibles = serie > M2_MAXIMO_PLAUSIBLE
    if implausibles.any():
        logger.warning(
            "Se anulan %d valores de %s por superar los %d m² "
            "(error de origen: ej. m² multiplicado por 1000)",
            int(implausibles.sum()),
            columna,
            M2_MAXIMO_PLAUSIBLE,
        )
        serie = serie.mask(implausibles)
    return serie


def normalizar_m2(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback en cadena por inconsistencia de las fuentes (supuesto del MVP):

    - m2_util  := m2_construida (detalle) -> m2_tarjeta
    - m2_total := m2_totales (detalle) -> m2_construida -> m2_tarjeta

    Los valores finales implausibles (> M2_MAXIMO_PLAUSIBLE m²) se anulan:
    son errores de digitación del anunciante y corromperían el modelo
    (además de desbordar el NUMERIC(8,2) de la tabla).
    """
    df = df.copy()
    df["m2_util"] = df["m2_construida"].fillna(df["m2_tarjeta"])
    df["m2_total"] = (
        df["m2_totales"].fillna(df["m2_construida"]).fillna(df["m2_tarjeta"])
    )
    df["m2_util"] = _anular_implausibles(df["m2_util"], "m2_util")
    df["m2_total"] = _anular_implausibles(df["m2_total"], "m2_total")
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
