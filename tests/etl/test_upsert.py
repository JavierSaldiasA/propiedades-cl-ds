"""Tests de src/etl/upsert.py: mapeo de valores y SQL generado (sin BD real)."""

from datetime import date

import pandas as pd

from src.etl.upsert import _filas_nativas, _sql_upsert, _valor_nativo


def test_valor_nativo_nulos():
    assert _valor_nativo(None) is None
    assert _valor_nativo(pd.NA) is None
    assert _valor_nativo(pd.NaT) is None
    assert _valor_nativo(float("nan")) is None


def test_valor_nativo_timestamp_a_date():
    assert _valor_nativo(pd.Timestamp("2026-08-01")) == date(2026, 8, 1)


def test_valor_nativo_pasa_valores_simples():
    assert _valor_nativo("UF") == "UF"
    assert _valor_nativo(350000.0) == 350000.0
    assert _valor_nativo(True) is True


def test_filas_nativas_convierte_tipos_nullable():
    df = pd.DataFrame(
        {
            "entero": pd.array([3, None], dtype="Int64"),
            "flotante": pd.array([55.5, None], dtype="Float64"),
            "booleano": pd.array([True, None], dtype="boolean"),
            "fecha": pd.to_datetime(["2026-08-01", None]),
            "texto": ["a", None],
        }
    )
    filas = _filas_nativas(df)
    assert filas[0] == (3, 55.5, True, date(2026, 8, 1), "a")
    assert filas[1] == (None, None, None, None, None)


def test_sql_upsert_actualiza_todo_menos_las_claves():
    columnas = ["fuente", "url_origen", "precio_valor", "fecha_scraping"]
    sql = _sql_upsert(columnas)
    assert "ON CONFLICT (fuente, url_origen) DO UPDATE SET" in sql
    assert "precio_valor = EXCLUDED.precio_valor" in sql
    assert "fecha_scraping = EXCLUDED.fecha_scraping" in sql
    # Las claves de conflicto no se actualizan
    clausula_set = sql.split("DO UPDATE SET")[1]
    assert "fuente = EXCLUDED.fuente" not in clausula_set
    assert "url_origen = EXCLUDED.url_origen" not in clausula_set
