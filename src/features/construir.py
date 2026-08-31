"""Feature engineering a partir de la tabla `properties` limpia.

Todas las funciones son puras: reciben un DataFrame y devuelven un DataFrame
(o un dict de setup), sin acceso a red, base de datos ni disco. Esto permite
testearlas offline con DataFrames sintéticos (ver `tests/features/`).

El setup (medianas de imputación, encodings, umbrales) se calcula con
`calcular_setup` sobre el conjunto de entrenamiento y luego se reutiliza tal
cual para transformar datos nuevos (score), evitando data leakage.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.features import config

logger = logging.getLogger(__name__)

# Columnas de identificación/contexto que no son features del modelo.
COLUMNAS_NO_FEATURES = [
    "url_origen",
    "fecha_publicacion",
    "fecha_scraping",
    "descripcion",
    "region",
    "tipo_operacion",
    "precio_clp_normalizado",
    "precio_moneda",
    "precio_valor",
    "m2_construida",
    "m2_totales",
    "m2_tarjeta",
    "anio_construccion",
]


def limpiar_precio(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra filas sin precio válido y deja `precio_clp_normalizado`.

    Se descartan filas con precio ausente o <= 0 (moneda inválida, avisos
    sin precio público). Devuelve el mismo DataFrame sin esas filas.
    """
    precio = pd.to_numeric(df[config.COLUMNA_PRECIO], errors="coerce")
    mascara_valido = precio.notna() & (precio > 0)
    n_descartados = int((~mascara_valido).sum())
    if n_descartados:
        logger.warning(
            "Se descartan %s filas sin precio válido (ausente o <= 0).",
            n_descartados,
        )
    return df[mascara_valido].copy()


def crear_target(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `precio_log = log1p(precio)` desde el precio ya validado."""
    out = df.copy()
    out[config.COLUMNA_TARGET] = np.log1p(
        pd.to_numeric(out[config.COLUMNA_PRECIO], errors="coerce")
    )
    return out


def crear_precio_por_m2(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `precio_por_m2_util` y `precio_por_m2_total` (NA si m2=0/NA)."""
    out = df.copy()
    precio = pd.to_numeric(out[config.COLUMNA_PRECIO], errors="coerce")
    for col in ("m2_util", "m2_total"):
        m2 = pd.to_numeric(out[col], errors="coerce")
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"precio_por_{col}"] = precio / m2
        out[f"precio_por_{col}"] = out[f"precio_por_{col}"].where(m2 > 0, np.nan)
    return out


def agregar_indicadores_faltantes(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega un flag binario `sin_<columna>` por cada columna con nulos."""
    out = df.copy()
    for col in config.COLUMNAS_CON_INDICADOR:
        serie = out.get(col)
        if serie is None:
            continue
        out[f"sin_{col}"] = serie.isna().astype("int8")
    return out


def _imputar_sin_agrupar(
    df: pd.DataFrame, col: str, setup: dict[str, Any]
) -> pd.DataFrame:
    """Imputa `col` con la mediana global del setup (fallback)."""
    out = df.copy()
    resultado = setup["globales"].get(col)
    if resultado is None:
        logger.warning("Sin setup global para %s; no se imputa.", col)
        return out
    mascara = out[col].isna()
    out.loc[mascara, col] = resultado
    return out


def _imputar_por_grupo(
    df: pd.DataFrame, col: str, grupo: str, setup: dict[str, Any]
) -> pd.DataFrame:
    """Imputa `col` con la mediana por grupo, cayendo a la global si falta."""
    out = df.copy()
    medianas = setup["medianas"].get(col, {})
    global_ = setup["globales"].get(col, np.nan)
    mascara = out[col].isna()
    if not mascara.any():
        return out
    nombres_grupo = out.loc[mascara, grupo].astype(str)
    grupos_faltantes = ~nombres_grupo.isin(medianas)
    valores = nombres_grupo.map(medianas).astype(float)
    valores = valores.mask(grupos_faltantes, global_)
    out.loc[mascara, col] = valores.values
    return out


def imputar_numericas(df: pd.DataFrame, setup: dict[str, Any]) -> pd.DataFrame:
    """Imputa las columnas numéricas según el setup (medianas por comuna)."""
    out = df.copy()
    for col, espec in config.NUMERICAS_IMPUTAR.items():
        if col not in out.columns:
            continue
        grupo = espec["grupo"]
        if grupo and grupo in out.columns:
            out = _imputar_por_grupo(out, col, grupo, setup)
        else:
            out = _imputar_sin_agrupar(out, col, setup)
    return out


def _agrupar_comunas_raras(df: pd.DataFrame, setup: dict[str, Any]) -> pd.DataFrame:
    """Recodifica comunas con pocos avisos como `comuna_otra`."""
    out = df.copy()
    comunas_validas = set(setup.get("comunas_frecuentes", []))
    if not comunas_validas:
        return out
    col = out["comuna"].astype(str)
    out["comuna"] = col.where(col.isin(comunas_validas), config.CATEGORIA_COMUNA_OTRA)
    return out


def codificar_comuna(df: pd.DataFrame, setup: dict[str, Any]) -> pd.DataFrame:
    """Target-mean encoding con smoothing para `comuna`.

    El encoding de una comuna es un promedio ponderado entre su media local
    y la media global, con peso proporcional a su nº de avisos (smoothing).
    Las comunas raras ya vienen fundidas en `comuna_otra` desde el setup.
    """
    out = df.copy()
    media = setup["target_media"]
    smooth = config.SMOOTHING_TARGET_ENCODING
    col = out["comuna"].astype(str)
    nombres = col.unique()
    nivelados = {}
    # Estadísticas por comuna a nivel global (aplican a score igual que train).
    stats = setup.get("comuna_target_stats", {})
    for nombre in nombres:
        local = stats.get(nombre)
        if local is None:
            valor = media
        else:
            media_local, n = local
            valor = (media_local * n + media * smooth) / (n + smooth)
        nivelados[nombre] = valor
    out["comuna_enc"] = col.map(nivelados).astype(float)
    return out.drop(columns=["comuna"])


def codificar_onehot(df: pd.DataFrame, setup: dict[str, Any], col: str) -> pd.DataFrame:
    """One-hot de una columna categórica usando las categorías del setup."""
    out = df.drop(columns=[col])
    categorias = setup["categorias"].get(col, [])
    for cat in categorias:
        out[f"{col}__{cat}"] = (df[col].astype(str) == cat).astype("int8")
    return out


def codificar_categorias(df: pd.DataFrame, setup: dict[str, Any]) -> pd.DataFrame:
    """Aplica los encodings configurados (one-hot y target-encoding)."""
    out = df
    for col in config.CATEGORICAS_ONEHOT:
        if col in out.columns:
            out = codificar_onehot(out, setup, col)
    if "comuna" in out.columns:
        out = _agrupar_comunas_raras(out, setup)
        out = codificar_comuna(out, setup)
    return out


def filtrar_outliers_precio(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta precios extremos por el método IQR sobre el log del precio.

    Usa el log para que el IQR no lo inflen los valores extremos. Los límites
    salen del propio DataFrame (por eso se aplica antes de fijar el setup).
    """
    out = df.copy()
    precio = out[config.COLUMNA_TARGET]
    q1, q3 = precio.quantile(0.25), precio.quantile(0.75)
    iqr = q3 - q1
    bajo = q1 - config.MULTIPLICADOR_IQR * iqr
    alto = q3 + config.MULTIPLICADOR_IQR * iqr
    mascara = precio.between(bajo, alto)
    n_descartados = int((~mascara).sum())
    if n_descartados:
        logger.warning(
            "Se descartan %s outliers de precio (IQR k=%s).",
            n_descartados,
            config.MULTIPLICADOR_IQR,
        )
    return out[mascara].copy()


def calcular_setup(
    df: pd.DataFrame, col_objetivo: str = config.COLUMNA_TARGET
) -> dict[str, Any]:
    """Calcula el setup (medianas, encodings, umbrales) sobre un dataset de fit.

    Este dict se persiste junto al modelo y se reutiliza en `construir_matriz`
    con `setup=` para transformar datos nuevos sin volver a encajar (sin
    data leakage).
    """
    objetivo = pd.to_numeric(df[config.COLUMNA_TARGET], errors="coerce")

    medianas: dict[str, dict[str, float]] = {}
    globales: dict[str, float] = {}
    for col in config.NUMERICAS_IMPUTAR:
        if col not in df.columns:
            continue
        serie = pd.to_numeric(df[col], errors="coerce")
        globales[col] = float(serie.median())
        medianas[col] = {
            str(g): float(v)
            for g, v in serie.groupby(df["comuna"].astype(str))
            .median()
            .dropna()
            .items()
        }

    # Comunas frecuentes (>= umbral de avisos) para agrupar las raras.
    comunas = df["comuna"].astype(str)
    conteos = comunas.value_counts().to_dict()
    comunas_frecuentes = [
        c for c, n in conteos.items() if n >= config.UMBRAL_COMUNA_MIN_AVISOS
    ]

    # Estadísticas por comuna sobre `comuna_otra` ya agrupada.
    comuna_agrupada = comunas.where(
        comunas.isin(comunas_frecuentes), config.CATEGORIA_COMUNA_OTRA
    )
    target_media = float(objetivo.mean())
    comuna_target_stats: dict[str, tuple[float, int]] = {}
    comuna_conteos: dict[str, int] = {}
    for g, sub in objetivo.to_frame(config.COLUMNA_TARGET).groupby(comuna_agrupada):
        n = int(sub[config.COLUMNA_TARGET].notna().sum())
        comuna_conteos[str(g)] = n
        if n:
            comuna_target_stats[str(g)] = (float(sub[config.COLUMNA_TARGET].mean()), n)

    categorias: dict[str, list[str]] = {}
    for col in config.CATEGORICAS_ONEHOT:
        if col in df.columns:
            orden = df[col].value_counts().sort_values(ascending=False).index.tolist()
            categorias[col] = [str(c) for c in orden]

    return {
        "globales": globales,
        "medianas": medianas,
        "comunas_frecuentes": comunas_frecuentes,
        "target_media": target_media,
        "comuna_target_stats": comuna_target_stats,
        "comuna_conteos": comuna_conteos,
        "categorias": categorias,
    }


def construir_matriz(
    df: pd.DataFrame,
    setup: dict[str, Any] | None = None,
    *,
    entrenamiento: bool = False,
) -> tuple[pd.DataFrame, pd.Series] | pd.DataFrame:
    """Construye la matriz de features (+ target) desde `properties`.

    - Si `setup` es None (y `entrenamiento=True`), calcula el setup sobre el
      propio DataFrame y lo encaja (fit).
    - Si `setup` se pasa, lo aplica directamente (transform) sin re-encajar,
      lo que garantiza el mismo tratamiento en train y en score.

    Devuelve `(X, y, setup)` al encajar (`entrenamiento=True`), o solo `X` al
    transformar con un `setup` dado.
    """
    out = limpiar_precio(df)
    out = crear_target(out)

    if setup is None:
        if not entrenamiento:
            raise ValueError(
                "Se necesita `setup` para transformar datos nuevos, o "
                "`entrenamiento=True` para ajustar uno nuevo."
            )
        # Los límites de outliers se calculan sobre el fit: aplicarlos en el
        # score a una sola fila degeneraría el IQR. Los datos nuevos ya pasan
        # por la limpieza/plausibilidad del ETL.
        out = filtrar_outliers_precio(out)
        setup = calcular_setup(out)

    out = crear_precio_por_m2(out)
    out = agregar_indicadores_faltantes(out)
    out = imputar_numericas(out, setup)
    out = codificar_categorias(out, setup)

    x = out.drop(
        columns=[
            c
            for c in COLUMNAS_NO_FEATURES + [config.COLUMNA_TARGET]
            if c in out.columns
        ]
    )
    y = out[config.COLUMNA_TARGET] if config.COLUMNA_TARGET in out.columns else None

    if y is not None and entrenamiento:
        return x, y, setup
    return x
