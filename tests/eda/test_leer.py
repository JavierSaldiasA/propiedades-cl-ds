"""Tests de `src/eda/leer.py` con psycopg y config mockeados."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.eda import leer

# Postgres entrega NUMERIC como str; ver docstring de NUMERICAS en leer.py.
PRECIO_STR = "150000000"

COLUMNAS = (
    "tipo_operacion",
    "fuente",
    "fecha_publicacion",
    "fecha_scraping",
    "precio_valor",
    "bodega",
)
DESCRIPTION = [(c,) for c in COLUMNAS]


class _CursorFake:
    def __init__(self, filas: list[tuple]):
        self.filas = filas
        self.execute_llamadas: list[tuple] = []
        self.description = DESCRIPTION

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, consulta, parametros=None):
        self.execute_llamadas.append((consulta, parametros))

    def fetchall(self):
        return self.filas


class _ConexionFake:
    def __init__(self, filas: list[tuple]):
        self._cursor = _CursorFake(filas)
        self.url = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return self._cursor


def _mockear_bd(monkeypatch, filas: list[tuple]) -> _ConexionFake:
    conexion = _ConexionFake(filas)
    monkeypatch.setattr(
        "src.eda.leer.obtener_configuraciones",
        lambda: SimpleNamespace(url_database="postgresql://test"),
    )
    monkeypatch.setattr("src.eda.leer.psycopg.connect", lambda url: conexion)
    return conexion


def test_ejecuta_consulta_parametrizada(monkeypatch):
    conexion = _mockear_bd(monkeypatch, filas=[])

    leer.cargar_properties("venta")

    assert len(conexion._cursor.execute_llamadas) == 1
    consulta, parametros = conexion._cursor.execute_llamadas[0]
    assert consulta == leer.SQL_PROPIEDADES
    assert "%s" in consulta
    assert parametros == ("venta",)
    assert "'venta'" not in consulta


def test_valor_inyectado_no_se_interpola_en_consulta(monkeypatch):
    conexion = _mockear_bd(monkeypatch, filas=[])

    inyectado = "venta' OR '1'='1"
    leer.cargar_properties(inyectado)

    consulta, parametros = conexion._cursor.execute_llamadas[0]
    assert consulta == leer.SQL_PROPIEDADES
    assert parametros == (inyectado,)
    assert inyectado not in consulta


def test_carga_devuelve_dataframe_tipado(monkeypatch):
    fila = (
        "venta",
        "yapo",
        pd.Timestamp("2026-08-01"),
        pd.Timestamp("2026-08-07"),
        PRECIO_STR,
        True,
    )
    _mockear_bd(monkeypatch, filas=[tuple(fila)])

    df = leer.cargar_properties("venta")

    assert list(df.columns) == list(COLUMNAS)
    assert df.loc[0, "fecha_publicacion"] == pd.Timestamp("2026-08-01")
    assert pd.api.types.is_datetime64_any_dtype(df["fecha_publicacion"])
    assert pd.api.types.is_numeric_dtype(df["precio_valor"])
    assert df["bodega"].dtype == "boolean"


def test_filas_vacias_devuelve_dataframe_vacio_con_columnas(monkeypatch):
    _mockear_bd(monkeypatch, filas=[])

    df = leer.cargar_properties("venta")

    assert df.empty
    assert list(df.columns) == list(COLUMNAS)
