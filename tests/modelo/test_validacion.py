"""Tests de la validación cruzada honesta del modelo."""

from __future__ import annotations

import pandas as pd
import pytest

from src.features.construir import construir_matriz
from src.modelo.validacion import (
    COLUMNAS_TAUTOLOGICAS,
    aplicar_clip,
    calcular_clip,
    evaluar_cv,
    modelos_baseline,
    preparar_ajuste,
    preparar_x,
)


def _matriz(df: pd.DataFrame, setup: dict) -> pd.DataFrame:
    x, _, _ = construir_matriz(df, setup=setup, entrenamiento=True)
    return preparar_x(x)


def test_evaluar_cv_ejecuta_todos_los_modelos(df_propiedades):
    por_fold, resumen = evaluar_cv(df_propiedades, n_folds=3, semilla=42)
    assert set(por_fold["modelo"]) == set(modelos_baseline(42))
    assert len(por_fold) == len(modelos_baseline(42)) * 3
    assert list(resumen["modelo"]) == sorted(
        resumen["modelo"],
        key=lambda m: resumen.loc[resumen["modelo"] == m, "mape_media"].iloc[0],
    )
    assert (resumen["mape_media"] > 0).all()
    assert (resumen["mape_media"] < 100).all()


def test_evaluar_cv_reproducible(df_propiedades):
    por_fold_a, _ = evaluar_cv(df_propiedades, n_folds=3, semilla=7)
    por_fold_b, _ = evaluar_cv(df_propiedades, n_folds=3, semilla=7)
    pd.testing.assert_frame_equal(por_fold_a, por_fold_b)


def test_trivial_mediana_es_piso(df_propiedades):
    _, resumen = evaluar_cv(df_propiedades, n_folds=3, semilla=42)
    mape_mediana = resumen.loc[resumen["modelo"] == "mediana", "mape_media"].iloc[0]
    mape_rf = resumen.loc[resumen["modelo"] == "random_forest", "mape_media"].iloc[0]
    mape_ridge = resumen.loc[resumen["modelo"] == "ridge", "mape_media"].iloc[0]
    assert mape_rf < mape_mediana
    assert mape_ridge < mape_mediana


def test_ridge_produce_metricas_finitas(df_propiedades):
    por_fold, _ = evaluar_cv(df_propiedades, n_folds=3, semilla=42)
    ridge = por_fold[por_fold["modelo"] == "ridge"]
    assert not ridge.empty
    assert ridge["mape"].notna().all()
    assert (ridge["mape"] > 0).all()


def test_preparar_ajuste_quita_outliers_y_fija_setup(df_propiedades):
    df_limpio, setup = preparar_ajuste(df_propiedades)
    assert "precio_log" in df_limpio.columns
    assert "target_media" in setup
    # El setup se reutiliza tal cual para score.
    x = _matriz(df_limpio, setup)
    assert list(x.columns) == list(_matriz(df_limpio, setup).columns)


def test_precio_por_m2_se_excluye_de_la_matriz(df_propiedades):
    df_limpio, setup = preparar_ajuste(df_propiedades)
    x = _matriz(df_limpio, setup)
    for col in COLUMNAS_TAUTOLOGICAS:
        assert col not in x.columns


def test_bodega_nulo_se_completa_como_false(df_propiedades):
    df_limpio, setup = preparar_ajuste(df_propiedades)
    x = _matriz(df_limpio, setup)
    assert "bodega" in x.columns
    assert not x["bodega"].isna().any()


def test_gastos_comunes_nulo_se_completa(df_propiedades):
    df_limpio, setup = preparar_ajuste(df_propiedades)
    x = _matriz(df_limpio, setup)
    assert "gastos_comunes" in x.columns
    assert not x["gastos_comunes"].isna().any()


def test_aplicar_clip_recorta_extremos(df_propiedades):
    df_limpio, setup = preparar_ajuste(df_propiedades)
    x = _matriz(df_limpio, setup)
    extremo = x.copy()
    extremo.loc[extremo.index[0], "m2_util"] = 100_001.0
    clip = calcular_clip(df_limpio, setup)
    recortado = aplicar_clip(extremo, clip)
    assert "m2_util" in clip
    alto = clip["m2_util"][1]
    assert alto < 100_001.0
    assert float(recortado.loc[recortado.index[0], "m2_util"]) == pytest.approx(alto)
