"""Tests de la persistencia del modelo (joblib)."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from src.modelo.persistencia import cargar_modelo, guardar_modelo, ruta_modelo


def test_ruta_modelo_especifica_por_operacion():
    ruta_venta = ruta_modelo("venta")
    ruta_arriendo = ruta_modelo("arriendo")
    assert ruta_venta.name == "modelo_venta.joblib"
    assert ruta_arriendo.name == "modelo_arriendo.joblib"
    assert ruta_venta != ruta_arriendo


def test_roundtrip_artefacto(tmp_path):
    modelo = RandomForestRegressor(n_estimators=5, random_state=0)
    x = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, 5.0], [4.0, 7.0]])
    y = np.array([3.0, 5.0, 8.0, 11.0])
    modelo.fit(x, y)
    artefacto = {
        "modelo": modelo,
        "setup": {"target_media": 1.5},
        "columnas": ["a", "b"],
        "resultados_cv": {"por_fold": {"mape": [1.0]}},
    }
    ruta = guardar_modelo(artefacto, tmp_path / "modelo.joblib")
    assert ruta.exists()

    cargado = cargar_modelo(ruta)
    np.testing.assert_allclose(cargado["modelo"].predict(x), modelo.predict(x))
    assert cargado["setup"] == artefacto["setup"]
    assert cargado["columnas"] == ["a", "b"]


def test_guardar_crea_directorio(tmp_path):
    ruta = tmp_path / "anidado" / "modelo.joblib"
    guardar_modelo({"modelo": None}, ruta)
    assert ruta.exists()
