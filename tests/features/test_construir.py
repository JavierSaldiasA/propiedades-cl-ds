"""Tests de src/features/construir.py con DataFrames sintéticos (sin BD)."""

import numpy as np
import pandas as pd
import pytest

from src.features.construir import (
    agregar_indicadores_faltantes,
    calcular_setup,
    codificar_categorias,
    construir_matriz,
    crear_precio_por_m2,
    crear_target,
    filtrar_outliers_precio,
    imputar_numericas,
    limpiar_precio,
)


def _df_fixture() -> pd.DataFrame:
    """DataFrame sintético con la forma de `properties` (schema del ETL)."""
    df = pd.DataFrame(
        {
            "fuente": ["toctoc", "toctoc", "pi", "pi", "yapo"],
            "url_origen": [f"https://portx.cl/aviso/{i}" for i in range(5)],
            "tipo_operacion": ["venta"] * 5,
            "tipo_propiedad": ["departamento", "casa", "departamento", "casa", "casa"],
            "precio_valor": [5000.0, 3000.0, 9000.0, 2500.0, 7000.0],
            "precio_moneda": ["UF"] * 5,
            "precio_clp_normalizado": [
                200_000_000,
                120_000_000,
                360_000_000,
                100_000_000,
                280_000_000,
            ],
            "m2_util": [60.0, 150.0, 55.0, 200.0, np.nan],
            "m2_total": [70.0, 300.0, 65.0, 350.0, np.nan],
            "gastos_comunes": [np.nan] * 5,
            "dormitorios": [2, 4, 2, 5, 3],
            "banos": [2, 3, 1, 4, 2],
            "estacionamientos": [1, 2, np.nan, 3, 1],
            "bodega": [False, True, np.nan, True, False],
            "comuna": [
                "Las Condes",
                "Las Condes",
                "Santiago",
                "Santiago",
                "Lo Barnechea",
            ],
            "region": ["Región Metropolitana"] * 5,
            "antiguedad_anios": [5, 20, np.nan, 15, 2],
            "descripcion": ["d1", "d2", "d3", "d4", "d5"],
            "fecha_publicacion": pd.to_datetime(["2026-08-01"] * 5),
            "fecha_scraping": pd.to_datetime(["2026-08-01"] * 5),
        }
    )
    return df


def test_limpiar_precio_filtra_no_validos():
    df = _df_fixture()
    df.loc[2, "precio_clp_normalizado"] = 0.0
    df.loc[3, "precio_clp_normalizado"] = pd.NA
    out = limpiar_precio(df)
    assert set(out["url_origen"]) == {
        "https://portx.cl/aviso/0",
        "https://portx.cl/aviso/1",
        "https://portx.cl/aviso/4",
    }


def test_crear_target_log1p():
    out = crear_target(_df_fixture())
    assert out["precio_log"].iloc[0] == pytest.approx(np.log1p(200_000_000), rel=1e-9)


def test_crear_precio_por_m2():
    out = crear_precio_por_m2(_df_fixture())
    esperado_util = 200_000_000 / 60.0
    assert out["precio_por_m2_util"].iloc[0] == pytest.approx(esperado_util)
    # m2 faltante -> NA (no +inf)
    assert pd.isna(out["precio_por_m2_util"].iloc[4])
    assert pd.isna(out["precio_por_m2_total"].iloc[4])


def test_agregar_indicadores_faltantes():
    out = agregar_indicadores_faltantes(_df_fixture())
    assert out["sin_m2_util"].tolist() == [0, 0, 0, 0, 1]
    assert out["sin_gastos_comunes"].tolist() == [1, 1, 1, 1, 1]
    assert out["sin_bodega"].tolist() == [0, 0, 1, 0, 0]


def test_calcular_setup_medianas_por_comuna():
    df = crear_target(_df_fixture())
    setup = calcular_setup(df)
    # m2_util mediana por comuna: Las Condes -> mediana(60,150) = 105
    assert setup["medianas"]["m2_util"]["Las Condes"] == pytest.approx(105.0)
    # m2_util: Santiago filas 2 y 3 -> 55 y 200 -> mediana 127.5
    assert setup["medianas"]["m2_util"]["Santiago"] == pytest.approx(127.5)
    # global de m2_total -> mediana(70,300,65,350) = 185
    assert setup["globales"]["m2_total"] == pytest.approx(185.0)
    # con solo 2 avisos por comuna, ninguna supera el umbral de 20
    assert setup["comunas_frecuentes"] == []


def test_imputar_numericas_por_comuna_con_fallback_global():
    df = crear_target(_df_fixture())
    setup = calcular_setup(df)
    out = imputar_numericas(df, setup)
    # fila 4 (Lo Barnechea) sin m2_util -> fallback a mediana global de m2_util
    assert pd.notna(out["m2_util"].iloc[4])
    # estacionamientos: el nan de la fila 2 (Santiago) -> mediana de
    # estacionamientos en Santiago (solo el 3) = 3
    assert out["estacionamientos"].iloc[2] == pytest.approx(3.0)


def test_calcular_setup_con_comunas_frecuentes():
    df = _df_fixture()
    df = pd.concat([df] * 12, ignore_index=True)  # 60 filas
    df["comuna"] = ["Las Condes"] * 30 + ["Santiago"] * 20 + ["Otra"] * 10
    df["precio_clp_normalizado"] = [100_000_000] * len(df)
    df = crear_target(df)
    setup = calcular_setup(df)
    assert "Las Condes" in setup["comunas_frecuentes"]
    assert "Santiago" in setup["comunas_frecuentes"]
    assert "Otra" not in setup["comunas_frecuentes"]  # solo 10 < 20
    # "Otra" se agrupa en la categoría residual
    assert "comuna_otra" in setup["comuna_target_stats"]


def test_codificar_comuna_target_encoding():
    df = _df_fixture()
    df = pd.concat([df] * 12, ignore_index=True)
    df["comuna"] = ["Las Condes"] * 30 + ["Santiago"] * 20 + ["Otra"] * 10
    df["precio_clp_normalizado"] = [100_000_000] * len(df)
    df = crear_target(df)
    setup = calcular_setup(df)
    out = codificar_categorias(df, setup)
    assert "comuna" not in out.columns
    assert "comuna_enc" in out.columns
    assert "comuna__" not in "".join(out.columns)  # no one-hot de comuna
    # Las Condes (media 100M) no debe caer bajo el prior global
    valor_lc = out.loc[:29, "comuna_enc"].iloc[0]
    assert valor_lc > 0


def test_filtrar_outliers_precio_iqr():
    df = _df_fixture()
    df = crear_target(df)
    # Reemplazo la fila 0 por un absurdo (17.2 B, como el outlier del EDA).
    df.loc[0, "precio_clp_normalizado"] = 17_200_000_000
    df.loc[0, "precio_log"] = np.log1p(17_200_000_000)
    out = filtrar_outliers_precio(df)
    assert "https://portx.cl/aviso/0" not in set(out["url_origen"])
    assert len(out) == 4


def test_construir_matriz_entrenamiento_devuelve_x_y_setup():
    df = _df_fixture()
    x, y, setup = construir_matriz(df, entrenamiento=True)
    assert isinstance(x, pd.DataFrame)
    assert isinstance(y, pd.Series)
    assert isinstance(setup, dict)
    # No quedan columnas de contexto/identificación en X
    assert (
        set(x.columns)
        & {
            "comuna",
            "precio_clp_normalizado",
            "descripcion",
            "url_origen",
            "precio_log",
        }
        == set()
    )
    for col in ("comuna_enc", "precio_por_m2_util", "sin_m2_util"):
        assert col in x.columns


def test_construir_matriz_transform_sin_setup_errores():
    with pytest.raises(ValueError):
        construir_matriz(_df_fixture())


def test_construir_matriz_transform_consistente_con_fit():
    df = _df_fixture()
    df = pd.concat([df] * 12, ignore_index=True)
    df["comuna"] = ["Las Condes"] * 30 + ["Santiago"] * 20 + ["Otra"] * 10
    df["precio_clp_normalizado"] = [100_000_000] * len(df)
    x_train, y_train, setup = construir_matriz(df, entrenamiento=True)
    x_score = construir_matriz(df, setup=setup)
    # Mismas columnas y por lo tanto el modelo puede reutilizarse.
    assert list(x_score.columns) == list(x_train.columns)
