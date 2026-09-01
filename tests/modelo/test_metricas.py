"""Tests de las métricas de regresión (log y CLP)."""

from __future__ import annotations

import numpy as np
import pytest

from src.modelo.metricas import metricas_regresion


def test_prediccion_perfecta():
    y = np.log1p(np.array([100_000, 500_000, 1_000_000]))
    metricas = metricas_regresion(y, y)
    assert metricas["mae_log"] == pytest.approx(0.0)
    assert metricas["rmse_log"] == pytest.approx(0.0)
    assert metricas["r2_log"] == pytest.approx(1.0)
    assert metricas["mae_clp"] == pytest.approx(0.0)
    assert metricas["rmse_clp"] == pytest.approx(0.0)
    assert metricas["mape"] == pytest.approx(0.0)


def test_metricas_valores_conocidos():
    precio = np.array([1_000_000, 2_000_000])
    prediccion = np.array([1_100_000, 1_900_000])
    metricas = metricas_regresion(np.log1p(precio), np.log1p(prediccion))
    # Errores en CLP: |-100k|+|100k| sobre 2 y MAPE 10% y 5% -> 7.5%.
    assert metricas["mae_clp"] == pytest.approx(100_000.0)
    assert metricas["rmse_clp"] == pytest.approx(100_000.0)
    assert metricas["mape"] == pytest.approx(7.5)


def test_mape_ignora_direccion_del_error():
    precio = np.array([1_000_000, 2_000_000])
    prediccion = np.array([900_000, 2_200_000])
    metricas = metricas_regresion(np.log1p(precio), np.log1p(prediccion))
    assert metricas["mape"] == pytest.approx(10.0)


def test_longitudes_incompatibles_abortan():
    with pytest.raises(ValueError):
        metricas_regresion(np.array([1.0, 2.0]), np.array([1.0]))


def test_vacio_aborta():
    with pytest.raises(ValueError):
        metricas_regresion(np.array([]), np.array([]))
