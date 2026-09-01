"""Tests de la CLI src/etl/cargar.py sin BD ni red (dobles de psycopg)."""

from pathlib import Path

import pandas as pd
import pytest

from src.etl import cargar


def _escribir_corrida(base: Path, run_id: str, filas: int = 1) -> Path:
    """Corrida de scraping simulada: <base>/<run_id>/propiedades.parquet.

    Devuelve `base` (el directorio raw esperado por DIRECTORIOS_RAW).
    """
    corrida = base / run_id
    corrida.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "url_origen": [f"https://www.yapo.cl/aviso/{i}" for i in range(filas)],
            "tipo_operacion": ["venta"] * filas,
            "tipo_propiedad": ["casa"] * filas,
            "precio_valor": pd.array([100.0] * filas, dtype="Float64"),
            "precio_moneda": ["UF"] * filas,
            "m2_construida": pd.array([50.0] * filas, dtype="Float64"),
            "m2_totales": pd.array([60.0] * filas, dtype="Float64"),
            "m2_tarjeta": pd.array([None] * filas, dtype="Float64"),
            "gastos_comunes": pd.array([None] * filas, dtype="Float64"),
            "dormitorios": pd.array([3] * filas, dtype="Int64"),
            "banos": pd.array([2] * filas, dtype="Int64"),
            "estacionamientos": pd.array([1] * filas, dtype="Int64"),
            "bodega": pd.array([None] * filas, dtype="boolean"),
            "comuna": ["Santiago"] * filas,
            "region": ["Región Metropolitana"] * filas,
            "descripcion": ["aviso de prueba"] * filas,
            "fecha_publicacion": pd.to_datetime(["2026-08-01"] * filas),
            "fecha_scraping": pd.to_datetime(["2026-08-02"] * filas),
            "anio_construccion": pd.array([2010] * filas, dtype="Int64"),
        }
    )
    df.to_parquet(corrida / "propiedades.parquet")
    return base


class _CursorFake:
    def __init__(self, existe: bool = True):
        self.ejecutados: list = []
        self.existe = existe

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.ejecutados.append((sql, params))

    def executemany(self, sql, datos):
        self.ejecutados.append((sql, datos))

    def fetchone(self):
        return ("properties",) if self.existe else (None,)


class _ConexionFake:
    def __init__(self, existe: bool = True):
        self.cursor_actual = _CursorFake(existe=existe)
        self.cerrada = False

    def cursor(self):
        return self.cursor_actual

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.cerrada = True


def _monkeypatch_psycopg(monkeypatch, conexion: _ConexionFake):
    def conectar(url_database):
        conexion.url = url_database
        return conexion

    monkeypatch.setattr(cargar.psycopg, "connect", conectar)


def test_ultimo_run_id(tmp_path):
    directorio = tmp_path / "yapo"
    for corrida in ("20260810_000000", "20260807_104024", "20260809_120000"):
        (directorio / corrida).mkdir(parents=True)
    (directorio / ".oculto").mkdir()
    assert cargar._ultimo_run_id(directorio) == "20260810_000000"
    assert cargar._ultimo_run_id(tmp_path / "sin_corridas") is None


def test_resolver_parquets_toma_la_ultima_de_cada_fuente(tmp_path, monkeypatch):
    yapo = _escribir_corrida(tmp_path / "yapo", "20260807_104024", 2)
    _escribir_corrida(tmp_path / "yapo", "20260810_000000", 3)
    _escribir_corrida(tmp_path / "toctoc", "20260809_120000", 1)
    monkeypatch.setattr(
        cargar,
        "DIRECTORIOS_RAW",
        {"yapo": yapo, "portal_inmobiliario": tmp_path / "portal_inmobiliario"},
    )
    resultado = cargar._resolver_parquets(["yapo", "portal_inmobiliario"], None)
    fuentes = [fuente for fuente, _ in resultado]
    assert fuentes == ["yapo"]  # portal sin corridas: se omite
    _, df = resultado[0]
    assert len(df) == 3  # la corrida más reciente


def test_resolver_parquets_run_id_explicito_aborta_si_no_existe(tmp_path, monkeypatch):
    _escribir_corrida(tmp_path / "yapo", "20260807_104024")
    monkeypatch.setattr(cargar, "DIRECTORIOS_RAW", {"yapo": tmp_path / "yapo"})
    with pytest.raises(SystemExit, match="No existe el parquet"):
        cargar._resolver_parquets(["yapo"], "20260811_000000")


def test_resolver_parquets_sin_corridas_aborta(tmp_path, monkeypatch):
    monkeypatch.setattr(cargar, "DIRECTORIOS_RAW", {"yapo": tmp_path / "yapo"})
    with pytest.raises(SystemExit, match="No hay corridas disponibles"):
        cargar._resolver_parquets(["yapo"], None)


def test_aplicar_schema(monkeypatch):
    conexion = _ConexionFake()
    _monkeypatch_psycopg(monkeypatch, conexion)
    cargar._aplicar_schema("postgres://db")
    assert conexion.url == "postgres://db"
    sql = conexion.cursor_actual.ejecutados[0][0]
    assert "CREATE TABLE IF NOT EXISTS properties" in sql


def test_aplicar_schema_cierra_conexion(monkeypatch):
    conexion = _ConexionFake()
    _monkeypatch_psycopg(monkeypatch, conexion)
    cargar._aplicar_schema("postgres://db")
    assert conexion.cerrada


def test_verificar_tabla_existe(monkeypatch):
    conexion = _ConexionFake(existe=True)
    _monkeypatch_psycopg(monkeypatch, conexion)
    cargar._verificar_tabla("postgres://db")  # no lanza


def test_verificar_tabla_faltante_aborta(monkeypatch):
    conexion = _ConexionFake(existe=False)
    _monkeypatch_psycopg(monkeypatch, conexion)
    with pytest.raises(SystemExit, match="La tabla properties no existe"):
        cargar._verificar_tabla("postgres://db")


@pytest.fixture
def config_fake():
    import types

    return types.SimpleNamespace(
        url_database="postgres://fake",
        usuario_bcch="u",
        password_bcch="p",
    )


def test_main_flujo_completo(tmp_path, monkeypatch, config_fake):
    """--crear-schema: schema + verificación + serie UF + procesado de una fuente."""
    directorio = tmp_path / "yapo"
    _escribir_corrida(directorio, "20260807_104024", 2)
    conexion = _ConexionFake()
    _monkeypatch_psycopg(monkeypatch, conexion)
    serie_uf = pd.Series([40000.0], index=pd.to_datetime(["2026-08-01"]))
    monkeypatch.setattr(cargar, "DIRECTORIOS_RAW", {"yapo": directorio})
    monkeypatch.setattr(cargar, "obtener_configuraciones", lambda: config_fake)
    monkeypatch.setattr(cargar, "obtener_serie_uf", lambda *a, **k: serie_uf)
    cargar.main(["--fuente", "yapo", "--crear-schema"])

    sqls = [sql for sql, _ in conexion.cursor_actual.ejecutados]
    assert any("CREATE TABLE IF NOT EXISTS properties" in s for s in sqls)
    assert any("ON CONFLICT (fuente, url_origen)" in s for s in sqls)
    assert conexion.cerrada


def test_main_sin_fuente_procesa_todas(tmp_path, monkeypatch, config_fake):
    directorio_yapo = _escribir_corrida(tmp_path / "yapo", "20260807_104024")
    directorio_toctoc = _escribir_corrida(tmp_path / "toctoc", "20260807_104024")
    conexion = _ConexionFake()
    _monkeypatch_psycopg(monkeypatch, conexion)
    serie_uf = pd.Series([40000.0], index=pd.to_datetime(["2026-08-01"]))
    monkeypatch.setattr(
        cargar,
        "DIRECTORIOS_RAW",
        {"yapo": directorio_yapo, "toctoc": directorio_toctoc},
    )
    monkeypatch.setattr(cargar, "obtener_configuraciones", lambda: config_fake)
    monkeypatch.setattr(cargar, "obtener_serie_uf", lambda *a, **k: serie_uf)
    cargar.main([])
    upserts = [
        s for s, _ in conexion.cursor_actual.ejecutados if "INSERT INTO properties" in s
    ]
    assert len(upserts) == 2


def test_main_run_id_requiere_fuente():
    with pytest.raises(SystemExit, match="--run-id requiere --fuente"):
        cargar.main(["--run-id", "20260807_104024"])


def test_parsear_argumentos_choices():
    args = cargar.parsear_argumentos(["--fuente", "yapo", "--crear-schema"])
    assert args.fuente == "yapo"
    assert args.crear_schema is True
