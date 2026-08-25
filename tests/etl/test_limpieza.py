"""Tests de src/etl/limpieza.py con DataFrames sintéticos (sin BD ni API)."""

import pandas as pd

from src.etl.limpieza import (
    COLUMNAS_PROPERTIES,
    M2_MAXIMO_PLAUSIBLE,
    PRECIOS_MAXIMOS_PLAUSIBLES,
    calcular_antiguedad,
    normalizar_m2,
    normalizar_precios,
    preparar_para_carga,
)

SERIE_UF = pd.Series([40000.0], index=pd.to_datetime(["2026-08-01"]))


def _df_crudo() -> pd.DataFrame:
    """Replica la forma del parquet crudo del scraper."""
    return pd.DataFrame(
        {
            "url_origen": [
                "https://www.yapo.cl/aviso/1",
                "https://www.yapo.cl/aviso/2",
                "https://www.yapo.cl/aviso/3",
            ],
            "tipo_operacion": ["venta", "arriendo", "venta"],
            "tipo_propiedad": ["casa", "departamento", "casa"],
            "precio_valor": pd.array([100.0, 350000.0, 50.0], dtype="Float64"),
            "precio_moneda": ["UF", "CLP", "UF"],
            "fecha_publicacion": pd.to_datetime(["2026-08-01", None, None]),
            "fecha_scraping": pd.to_datetime(["2026-08-01"] * 3),
            "m2_construida": pd.array([55.0, None, None], dtype="Float64"),
            "m2_totales": pd.array([60.0, None, None], dtype="Float64"),
            "m2_tarjeta": pd.array([50.0, 70.0, None], dtype="Float64"),
            "gastos_comunes": pd.array([85000.0, None, None], dtype="Float64"),
            "dormitorios": pd.array([3, 2, None], dtype="Int64"),
            "banos": pd.array([2, 1, None], dtype="Int64"),
            "estacionamientos": pd.array([1, None, None], dtype="Int64"),
            "bodega": pd.array([True, None, None], dtype="boolean"),
            "comuna": ["Santiago", "Las Condes", "Macul"],
            "region": ["Región Metropolitana"] * 3,
            "descripcion": ["desc 1", "desc 2", None],
            "anio_construccion": pd.array([2010, None, 2030], dtype="Int64"),
        }
    )


def _pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Cadena completa de limpieza, tal como la ejecuta el CLI."""
    df = normalizar_precios(df, SERIE_UF)
    df = normalizar_m2(df)
    df = calcular_antiguedad(df)
    return preparar_para_carga(df)


def test_normalizar_precios():
    df = normalizar_precios(_df_crudo(), SERIE_UF)
    # UF con fecha de publicación
    assert df["precio_clp_normalizado"][0] == 4000000.0
    # CLP pasa directo
    assert df["precio_clp_normalizado"][1] == 350000.0
    # UF sin fecha de publicación -> usa fecha de scraping
    assert df["precio_clp_normalizado"][2] == 2000000.0


def test_normalizar_precios_valor_faltante():
    df = _df_crudo()
    df.loc[0, "precio_valor"] = pd.NA
    df = normalizar_precios(df, SERIE_UF)
    assert pd.isna(df["precio_clp_normalizado"][0])


def test_normalizar_precios_anula_error_de_moneda():
    """Monto CLP tipeado con moneda UF (caso real Yapo 32850692) -> NA."""
    df = _df_crudo()
    df.loc[0, "precio_valor"] = pd.array([125_000_000.0], dtype="Float64")
    df = normalizar_precios(df, SERIE_UF)
    assert pd.isna(df["precio_valor"][0])  # 125M UF > tope de UF
    assert pd.isna(df["precio_clp_normalizado"][0])  # ≈ 5×10¹² CLP


def test_normalizar_precios_conserva_legitimos():
    """El umbral no toca precios legítimos altos (incl. bordes exactos)."""
    df = _df_crudo()
    df.loc[0, "precio_valor"] = pd.array(
        [float(PRECIOS_MAXIMOS_PLAUSIBLES["UF"])], dtype="Float64"
    )  # borde exacto UF
    df.loc[1, "precio_valor"] = pd.array(
        [float(PRECIOS_MAXIMOS_PLAUSIBLES["CLP"])], dtype="Float64"
    )  # borde exacto CLP (1.900M real: máximo legítimo observado)
    df = normalizar_precios(df, SERIE_UF)
    assert df["precio_valor"][0] == 500_000.0
    assert df["precio_valor"][1] == 10_000_000_000.0
    # 500.000 UF × 40.000 CLP/UF = 2×10¹⁰ < 10¹²: no desborda NUMERIC(14,2)
    assert df["precio_clp_normalizado"][0] == 20_000_000_000.0


def test_normalizar_precios_conserva_terreno_lujo():
    """Terreno 2.453 m² en Vitacura a 105.000 UF (caso real TOCTOC
    4243995) sigue siendo legítimo tras subir el umbral a 500.000 UF."""
    df = _df_crudo()
    df.loc[0, "precio_valor"] = pd.array([105_000.0], dtype="Float64")
    df = normalizar_precios(df, SERIE_UF)
    assert df["precio_valor"][0] == 105_000.0
    assert df["precio_clp_normalizado"][0] == 4_200_000_000.0  # 105.000 × 40.000


def test_normalizar_precios_anulacion_no_toca_otras_columnas():
    df = _df_crudo()
    df.loc[0, "precio_valor"] = pd.array([125_000_000.0], dtype="Float64")
    df = normalizar_precios(df, SERIE_UF)
    # el aviso sobrevive completo: solo el precio se anula
    assert df["precio_moneda"][0] == "UF"
    assert df["m2_tarjeta"][0] == 50.0
    assert df["comuna"][0] == "Santiago"


def test_normalizar_m2_fallback_en_cadena():
    df = normalizar_m2(_df_crudo())
    # util: construida -> tarjeta
    assert df["m2_util"][0] == 55.0
    assert df["m2_util"][1] == 70.0
    assert pd.isna(df["m2_util"][2])
    # total: totales -> construida -> tarjeta
    assert df["m2_total"][0] == 60.0
    assert df["m2_total"][1] == 70.0


def test_normalizar_m2_anula_error_de_dedo():
    """m² multiplicado por 1000 por el anunciante -> NA, no 1.800.000."""
    df = _df_crudo()
    df.loc[0, "m2_construida"] = pd.NA
    df.loc[0, "m2_totales"] = pd.NA
    df.loc[0, "m2_tarjeta"] = 1_800_000.0
    df = normalizar_m2(df)
    assert pd.isna(df["m2_util"][0])
    assert pd.isna(df["m2_total"][0])


def test_normalizar_m2_conserva_valores_plausibles():
    """El umbral no toca superficies legítimas (incl. terrenos grandes)."""
    df = _df_crudo()
    for fila, m2 in (
        (0, float(M2_MAXIMO_PLAUSIBLE)),  # borde exacto
        (1, 1_365.0),  # máximo legítimo observado
        (2, 10_000.0),  # terreno grande legítimo
    ):
        df.loc[fila, "m2_construida"] = pd.NA
        df.loc[fila, "m2_totales"] = pd.NA
        df.loc[fila, "m2_tarjeta"] = m2
    df = normalizar_m2(df)
    assert df["m2_util"][0] == 100_000.0
    assert df["m2_util"][1] == 1_365.0
    assert df["m2_util"][2] == 10_000.0


def test_normalizar_m2_anulacion_no_toca_otras_columnas():
    df = _df_crudo()
    df.loc[0, "m2_construida"] = pd.NA
    df.loc[0, "m2_tarjeta"] = 1_800_000.0
    df = normalizar_m2(df)
    # el aviso sobrevive completo: solo el m² se anula
    assert df["precio_valor"][0] == 100.0
    assert df["dormitorios"][0] == 3
    assert df["comuna"][0] == "Santiago"


def test_calcular_antiguedad():
    df = calcular_antiguedad(_df_crudo())
    assert df["antiguedad_anios"][0] == 16  # 2026 - 2010
    assert pd.isna(df["antiguedad_anios"][1])  # sin año -> NA
    assert df["antiguedad_anios"][2] == 0  # año futuro -> clip a 0


def test_preparar_para_carga_columnas_y_fuente():
    df = _pipeline(_df_crudo())
    assert list(df.columns) == COLUMNAS_PROPERTIES
    assert (df["fuente"] == "yapo").all()


def test_preparar_para_carga_descarta_sin_url():
    df = _df_crudo()
    df.loc[1, "url_origen"] = None
    df = _pipeline(df)
    assert len(df) == 2
    assert df["url_origen"].notna().all()


def test_preparar_para_carga_dedup_conserva_la_ultima():
    df = _df_crudo()
    duplicada = df.iloc[[0]].copy()
    duplicada["precio_valor"] = pd.array([200.0], dtype="Float64")
    df = pd.concat([df, duplicada], ignore_index=True)
    df = _pipeline(df)
    assert len(df) == 3
    fila = df[df["url_origen"] == "https://www.yapo.cl/aviso/1"]
    assert fila["precio_valor"].iloc[0] == 200.0
