"""Tests de src/etl/esquema.py: la spec única genera un DDL consistente."""

from src.etl.esquema import (
    CHECK_FUENTE,
    CHECK_MONEDA,
    CHECK_OPERACION,
    COLUMNAS_CONFLICTO,
    COLUMNAS_PROPERTIES,
    TIPOS_SQL,
    generar_schema,
)


def test_todas_las_columnas_tienen_tipo_sql():
    assert set(COLUMNAS_PROPERTIES) == set(TIPOS_SQL)


def test_ddl_define_todas_las_columnas():
    sql = generar_schema()
    for columna in COLUMNAS_PROPERTIES:
        assert f"{columna} " in sql


def test_ddl_incluye_tipos_y_not_nulls():
    sql = generar_schema()
    assert "precio_valor NUMERIC(14, 2)" in sql
    assert "dormitorios SMALLINT" in sql
    assert "fuente TEXT NOT NULL" in sql
    assert "fecha_scraping DATE NOT NULL" in sql


def test_ddl_incluye_checks():
    sql = generar_schema()
    assert CHECK_FUENTE in sql
    assert CHECK_OPERACION in sql
    assert CHECK_MONEDA in sql


def test_ddl_incluye_unique_de_dedup():
    sql = generar_schema()
    union = ", ".join(COLUMNAS_CONFLICTO)
    assert f"UNIQUE ({union})" in sql


def test_ddl_es_idempotente():
    assert "CREATE TABLE IF NOT EXISTS properties" in generar_schema()
