"""Tests de src/etl/uf.py con serie UF sintética (sin llamadas a la API)."""

import pandas as pd
import pytest

from src.etl import uf
from src.etl.uf import convertir_a_clp, valor_uf_en_fecha


@pytest.fixture
def serie_uf():
    # Con días faltantes a propósito, para probar el fallback asof
    fechas = pd.to_datetime(["2026-08-01", "2026-08-03", "2026-08-05"])
    return pd.Series([40000.0, 40100.0, 40200.0], index=fechas)


@pytest.fixture(autouse=True)
def _cache_uf_vacia():
    """Cada test parte sin caché de serie UF."""
    uf._CACHE.clear()
    yield
    uf._CACHE.clear()


def _serie_sintetica():
    fechas = pd.to_datetime(["2026-08-01", "2026-08-02"])
    return pd.Series([40000.0, 40050.0], index=fechas)


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


def test_obtener_serie_uf_descarga_exitosamente(monkeypatch):
    serie = _serie_sintetica()
    llamadas = []

    def _falsa(desde, hasta, usuario, password):
        llamadas.append((desde, hasta, usuario, password))
        return serie

    monkeypatch.setattr(uf, "_descargar_serie_bcch", _falsa)
    resultado = uf.obtener_serie_uf(
        "2026-08-01", "2026-08-05", usuario="u", password="p"
    )
    pd.testing.assert_series_equal(resultado, serie)


def test_obtener_serie_uf_reusa_caché(monkeypatch):
    serie = _serie_sintetica()
    llamadas = []

    def _falsa(desde, hasta, usuario, password):
        llamadas.append(1)
        return serie

    monkeypatch.setattr(uf, "_descargar_serie_bcch", _falsa)
    uf.obtener_serie_uf("2026-08-01", "2026-08-05", usuario="u", password="p")
    uf.obtener_serie_uf("2026-08-01", "2026-08-05", usuario="u", password="p")
    assert len(llamadas) == 1


def test_obtener_serie_uf_reintenta_errores_transitorios(monkeypatch, caplog):
    serie = _serie_sintetica()
    intentos = []

    def _falsa(desde, hasta, usuario, password):
        intentos.append(1)
        if len(intentos) < 3:
            raise ConnectionError("red caída")
        return serie

    monkeypatch.setattr(uf, "_descargar_serie_bcch", _falsa)

    def _noop(_):
        return None

    monkeypatch.setattr(uf.time, "sleep", _noop)
    with caplog.at_level("WARNING"):
        resultado = uf.obtener_serie_uf(
            "2026-08-01", "2026-08-05", usuario="u", password="p"
        )
    assert len(intentos) == 3
    assert "intento" in caplog.text
    pd.testing.assert_series_equal(resultado, serie)


def test_obtener_serie_uf_agota_reintentos_y_relanza(monkeypatch):
    def _falsa(desde, hasta, usuario, password):
        raise ConnectionError("red caída")

    monkeypatch.setattr(uf, "_descargar_serie_bcch", _falsa)
    sleeps = []
    monkeypatch.setattr(uf.time, "sleep", sleeps.append)
    with pytest.raises(ConnectionError):
        uf.obtener_serie_uf("2026-08-01", "2026-08-05", usuario="u", password="p")
    assert len(sleeps) == uf.REINTENTOS - 1


def test_obtener_serie_uf_usa_credenciales_de_config(monkeypatch):
    serie = _serie_sintetica()
    config_fake = {"usuario_bcch": "conf_u", "password_bcch": "conf_p"}
    credenciales_vistas = []

    def _config():
        return type("Config", (), config_fake)()

    monkeypatch.setattr("src.config.obtener_configuraciones", _config)

    def _falsa(desde, hasta, usuario, password):
        credenciales_vistas.append((usuario, password))
        return serie

    monkeypatch.setattr(uf, "_descargar_serie_bcch", _falsa)
    resultado = uf.obtener_serie_uf("2026-08-01", "2026-08-05")
    assert credenciales_vistas == [("conf_u", "conf_p")]
    pd.testing.assert_series_equal(resultado, serie)
