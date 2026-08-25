"""Tests del modo --reparsear de src/scraping/toctoc.py (sin red)."""

import gzip
import json
from pathlib import Path

import pandas as pd

from src.scraping import toctoc

FIXTURES = Path(__file__).parent / "fixtures"


def _guardar_gzip(ruta: Path, texto: str) -> None:
    with gzip.open(ruta, "wt", encoding="utf-8") as archivo:
        archivo.write(texto)


def test_reparsear_regenera_parquet_con_campos_nuevos(tmp_path, monkeypatch):
    """Re-parsea snapshots reales y verifica listado + merge de ficha."""
    monkeypatch.setattr(toctoc, "DIRECTORIO_RAW", tmp_path)
    run = "20260825_120000"
    html_dir = tmp_path / run / "html"
    html_dir.mkdir(parents=True)
    _guardar_gzip(
        html_dir / "listado_venta_p1.json.gz",
        (FIXTURES / "toctoc_listado_venta.json").read_text(encoding="utf-8"),
    )
    _guardar_gzip(
        html_dir / "detalle_4231011.html.gz",
        (FIXTURES / "toctoc_ficha_venta_particular.html").read_text(encoding="utf-8"),
    )

    toctoc._reparsear(run)

    corridas = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert corridas == [run, corridas[-1]]  # el original intacto + uno nuevo
    df = pd.read_parquet(tmp_path / corridas[-1] / "propiedades.parquet")
    assert len(df) == 510

    # campos nuevos del parser de listado
    fila = df[df["adid"] == "4231011"].iloc[0]
    assert fila["dormitorios"] == 2
    assert fila["banos"] == 2
    assert float(fila["m2_construida"]) == 60.0
    assert str(fila["fecha_scraping"].date()) == "2026-08-25"  # fecha del run_id

    # merge de la ficha (region y descripción no vienen del listado)
    assert fila["region"] == "Metropolitana"
    assert "metro Matucana" in fila["descripcion"]
    # url_origen conserva la del listado (no la canónica con hash de la ficha)
    assert fila["url_origen"].endswith("4231011")


def test_reparsear_sin_snapshots_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(toctoc, "DIRECTORIO_RAW", tmp_path)
    try:
        toctoc._reparsear("20990101_000000")
    except SystemExit as error:
        assert "snapshots" in str(error)
    else:
        raise AssertionError("debía fallar sin directorio de snapshots")


def test_leer_gzip_roundtrip(tmp_path):
    ruta = tmp_path / "x.json.gz"
    toctoc._guardar_gzip(ruta, '{"a": 1}')
    assert json.loads(toctoc._leer_gzip(ruta)) == {"a": 1}
