"""Tests de src/etl/uf.py con serie UF sintética (sin llamadas a la API)."""

import pandas as pd
import pytest

from src.etl.uf import convertir_a_clp, valor_uf_en_fecha


@pytest.fixture
def serie_uf():
    # Con días faltantes a propósito, para probar el fallback asof
    fechas = pd.to_datetime(["2026-08-01", "2026-08-03", "2026-08-05"])
    return pd.Series([40000.0, 40100.0, 40200.0], index=fechas)


def test_valor_uf_dia_exacto(serie_uf):
    assert valor_uf_en_fecha(serie_uf, "2026-08-03") == 40100.0


def test_valor_uf_cae_al_dia_anterior_disponible(serie_uf):
    assert valor_uf_en_fecha(serie_uf, "2026-08-04") == 40100.0
    assert valor_uf_en_fecha(serie_uf, "2026-08-07") == 40200.0


def test_valor_uf_anterior_al_rango_es_none(serie_uf):
    assert valor_uf_en_fecha(serie_uf, "2026-07-31") is None


@pytest.mark.parametrize("fecha", [None, pd.NaT])
def test_valor_uf_fecha_nula(serie_uf, fecha):
    assert valor_uf_en_fecha(serie_uf, fecha) is None


def test_valor_uf_serie_vacia():
    assert valor_uf_en_fecha(pd.Series(dtype="float64"), "2026-08-01") is None


def test_convertir_clp_pasa_directo(serie_uf):
    assert convertir_a_clp(350000.0, "CLP", "2026-08-05", serie_uf) == 350000.0


def test_convertir_uf_multiplica_por_uf_de_la_fecha(serie_uf):
    assert convertir_a_clp(100.0, "UF", "2026-08-05", serie_uf) == 4020000.0


def test_convertir_uf_sin_valor_uf_es_none(serie_uf):
    assert convertir_a_clp(100.0, "UF", "2026-07-31", serie_uf) is None


def test_convertir_moneda_desconocida_es_none(serie_uf):
    assert convertir_a_clp(100.0, "USD", "2026-08-05", serie_uf) is None


@pytest.mark.parametrize("valor", [None, pd.NA])
def test_convertir_valor_nulo_es_none(serie_uf, valor):
    assert convertir_a_clp(valor, "UF", "2026-08-05", serie_uf) is None
