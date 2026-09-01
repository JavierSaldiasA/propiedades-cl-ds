"""Validación cruzada honesta del modelo de valoración.

El target-mean encoding de `comuna` se recalcula por fold (`construir_matrices_fold`),
así que el target de la validación nunca entra en los features con los que se
predice. El setup global (medianas, one-hot, umbrales, outliers) se ajusta una
sola vez sobre todo el dataset antes de partir los folds.

Aquí también se excluyen de la matriz las features `precio_por_m2_*`: se derivan
del mismo precio que es el target, con lo que el modelo podría reconstruirlo como
una tautología (precio = m² × ratio) y las métricas dejarían de medir capacidad
de predicción.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features.construir import (
    calcular_setup,
    construir_matrices_fold,
    construir_matriz,
    crear_target,
    filtrar_outliers_precio,
    limpiar_precio,
)
from src.modelo.metricas import metricas_regresion

# Features derivadas directamente del target (precio): el modelo las usaría para
# reconstruir el precio y no aprendería nada. Se excluyen de X en el modelado.
COLUMNAS_TAUTOLOGICAS = ["precio_por_m2_util", "precio_por_m2_total"]

# Winsorización de las features numéricas: las colas pesadas de los datos reales
# (gastos comunes o m² extremos) hacen explotar la extrapolación de los modelos
# lineales (predicciones absurdas que destruyen el RMSE en CLP). Se recortan al
# rango [CUANTIL_INF, CUANTIL_SUP] calculado sobre todo el dataset (igual que el
# resto del setup global).
CLIP_CUANTILES = (0.01, 0.99)

# Columnas que el feature engineering aún no imputa y que pueden llegar con nulos
# de la BD. Se completan con un valor neutral conservando la señal de ausencia en
# el flag `sin_<columna>` (o en el propio nulo, en el caso de `bodega`).
COLUMNAS_NULAS_NO_IMPUTADAS = {
    "bodega": False,
    "gastos_comunes": 0.0,
}


class _Mediana:
    """Predictor trivial: devuelve la mediana del target del train."""

    def __init__(self) -> None:
        self._valor: float = 0.0

    def fit(self, x: Any, y: Any) -> _Mediana:
        self._valor = float(np.median(np.asarray(y, dtype=float)))
        return self

    def predict(self, x: Any) -> np.ndarray:
        return np.full(len(x), self._valor)


def modelos_baseline(semilla: int) -> dict[str, Callable[[], Any]]:
    """Fábricas de modelos baseline (una instancia fresca por fold).

    Incluye el trivial `mediana`, que fija el piso que cualquier modelo real
    debe superar para justificarse, y `ridge` (regresión lineal regularizada
    con escalado estandarizado), el baseline clásico e interpretable.
    """
    return {
        "mediana": _Mediana,
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=200,
            min_samples_leaf=2,
            random_state=semilla,
            n_jobs=-1,
        ),
        "hist_gradient_boosting": lambda: HistGradientBoostingRegressor(
            max_iter=300,
            random_state=semilla,
        ),
    }


def preparar_x(x: pd.DataFrame) -> pd.DataFrame:
    """Limpia la matriz para el modelo.

    Excluye las features tautológicas y completa los nulos que el feature
    engineering deja pasar (un `bodega` ausente se interpreta como "sin
    bodega").
    """
    out = x.drop(columns=[c for c in COLUMNAS_TAUTOLOGICAS if c in x.columns])
    for col, valor in COLUMNAS_NULAS_NO_IMPUTADAS.items():
        if col in out.columns and out[col].isna().any():
            out = out.copy()
            out[col] = out[col].fillna(valor)
            if col == "bodega":
                out[col] = out[col].astype(bool)
    return out


def preparar_ajuste(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Deja el dataset listo para ajustar: sin outliers y con el setup global.

    El filtrado de outliers y el setup se hacen una sola vez sobre todo el
    conjunto (el modelo nuevo no re-encaja por fold), devolviendo el DataFrame
    ya saneado y el setup para reutilizar en score.
    """
    df_limpio = filtrar_outliers_precio(crear_target(limpiar_precio(df)))
    setup = calcular_setup(df_limpio)
    return df_limpio, setup


def calcular_clip(
    df_limpio: pd.DataFrame, setup: dict[str, Any]
) -> dict[str, tuple[float, float]]:
    """Límites de winsorización por feature, un diccionario {columna: (bajo, alto)}.

    Se calculan sobre la matriz completa del dataset (como el resto del setup
    global) y solo para columnas numéricas continuas; las flags 0/1 y bodega no
    se recortan.
    """
    x = construir_matriz(df_limpio, setup=setup, entrenamiento=True)[0]
    x = preparar_x(x)
    q_bajo, q_alto = CLIP_CUANTILES
    clip: dict[str, tuple[float, float]] = {}
    for col in x.columns:
        serie = x[col]
        if not pd.api.types.is_numeric_dtype(serie):
            continue
        if pd.api.types.is_bool_dtype(serie):
            continue
        bajo = float(serie.quantile(q_bajo))
        alto = float(serie.quantile(q_alto))
        if alto > bajo:
            clip[col] = (bajo, alto)
    return clip


def aplicar_clip(x: pd.DataFrame, clip: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Recorta las features numéricas a los límites de winsorización."""
    columnas = [c for c in clip if c in x.columns]
    if not columnas:
        return x
    out = x.copy()
    for col in columnas:
        bajo, alto = clip[col]
        out[col] = out[col].clip(bajo, alto)
    return out


def _metricas_por_fold(nombre: str, fold: int, y_val: pd.Series, y_pred: Any) -> dict:
    fila = {"modelo": nombre, "fold": fold, "n_val": int(len(y_val))}
    fila.update(metricas_regresion(y_val, y_pred))
    return fila


def evaluar_cv(
    df: pd.DataFrame,
    n_folds: int = 5,
    semilla: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """CV honesto (KFold) sobre el df, reportando métricas por fold y resumen.

    Devuelve `(por_fold, resumen)`. `resumen` agrega por modelo la media (± std)
    de cada métrica y ordena por la media del MAPE ascendente (mejor primero).
    Las predicciones del trivial `mediana` se calculan con la mediana del train
    de cada fold.
    """
    df_limpio, setup = preparar_ajuste(df)
    clip = calcular_clip(df_limpio, setup)
    kfold = KFold(n_splits=n_folds, shuffle=True, random_state=semilla)
    fabricas = modelos_baseline(semilla)

    filas: list[dict[str, Any]] = []
    for fold, (idx_train, idx_val) in enumerate(kfold.split(df_limpio), start=1):
        df_train = df_limpio.iloc[idx_train]
        df_val = df_limpio.iloc[idx_val]
        x_train, y_train, x_val, y_val = construir_matrices_fold(
            df_train, df_val, setup
        )
        x_train = aplicar_clip(preparar_x(x_train), clip)
        x_val = aplicar_clip(preparar_x(x_val), clip)
        for nombre, fabrica in fabricas.items():
            modelo = fabrica()
            modelo.fit(x_train, y_train)
            y_pred = modelo.predict(x_val)
            filas.append(_metricas_por_fold(nombre, fold, y_val, y_pred))

    por_fold = pd.DataFrame(filas)
    resumen = _resumen_cv(por_fold)
    return por_fold, resumen


def _agregar(por_fold: pd.DataFrame, grupo: pd.DataFrame, col: str) -> dict[str, float]:
    """Media y desviación de una métrica para un modelo."""
    media = float(grupo[col].mean())
    desv = float(grupo[col].std()) if len(grupo) > 1 else 0.0
    return {f"{col}_media": media, f"{col}_desv": desv}


def _resumen_cv(por_fold: pd.DataFrame) -> pd.DataFrame:
    """Agrega las métricas por modelo: media ± std, ordenadas por MAPE."""
    lineas: list[dict[str, Any]] = []
    metricas = [
        "mae_log",
        "rmse_log",
        "r2_log",
        "mae_clp",
        "rmse_clp",
        "mape",
    ]
    for nombre, grupo in por_fold.groupby("modelo", sort=False):
        linea: dict[str, Any] = {"modelo": nombre}
        for col in metricas:
            linea.update(_agregar(por_fold, grupo, col))
        linea["n_avisos"] = int(grupo["n_val"].sum())
        lineas.append(linea)
    return (
        pd.DataFrame(lineas)
        .sort_values("mape_media", ascending=True)
        .reset_index(drop=True)
    )
