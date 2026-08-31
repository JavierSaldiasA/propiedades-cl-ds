"""Tests del orquestador compartido (src/scraping/base.py), sin red real.

Cubre el esqueleto común: construcción del DataFrame desde registros,
merge de detalle, y el flujo de detalles sobre un cliente HTTP simulado.
"""

import argparse
import gzip
from pathlib import Path

import httpx
import pandas as pd

from src.scraping import base
from src.scraping.yapo import ScraperYapo
from src.scraping.yapo_detalle import parsear_detalle
from src.scraping.yapo_listado import parsear_tarjetas

FIXTURES = Path(__file__).parent / "fixtures"


def _args(**kwargs) -> argparse.Namespace:
    valores = {"categorias": [], "max_paginas": 5, "max_detalles": 1, "delay": 0.0}
    valores.update(kwargs)
    return argparse.Namespace(**valores)


def _cliente_mock(html: str, status: int = 200) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text=html))
    )


def test_a_dataframe_columnas_y_tipos():
    registros = {
        "1": {
            "adid": "1",
            "url_origen": "https://x.cl/1",
            "precio_valor": 100.0,
            "dormitorios": 2,
            "piscina": True,
            "fecha_scraping": pd.Timestamp("2026-08-01"),
        }
    }
    df = base.a_dataframe(registros)
    assert list(df.columns) == base.COLUMNAS
    assert df["dormitorios"].dtype.name == "Int64"
    assert df["precio_valor"].dtype.name == "Float64"
    assert df["piscina"].dtype.name == "boolean"


def test_escribir_parquet_de_roundtrip(tmp_path):
    base.escribir_parquet(
        {"1": {"adid": "1", "url_origen": "https://x.cl/1"}}, tmp_path
    )
    assert (tmp_path / "propiedades.parquet").exists()
    df = pd.read_parquet(tmp_path / "propiedades.parquet")
    assert len(df) == 1
    assert df["adid"][0] == "1"


def test_escribir_parquet_vacio_no_escribe(tmp_path):
    base.escribir_parquet({}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_fusionar_detalle_protege_url():
    registro = {"url_origen": "https://x.cl/1", "comuna": "Santiago"}
    detalle = {"url_origen": "https://canonica/1", "region": "RM"}
    base.fusionar_detalle(registro, detalle, proteger_url=True)
    assert registro["url_origen"] == "https://x.cl/1"  # no se sobrescribe
    assert registro["region"] == "RM"

    registro2 = {"url_origen": "https://x.cl/1"}
    base.fusionar_detalle(registro2, {"url_origen": "https://canonica/1"})
    assert registro2["url_origen"] == "https://canonica/1"


def test_scrapear_detalles_merge_sobre_tarjeta(tmp_path):
    """El detalle real de Yapo enriquece la tarjeta del listado (sin red)."""
    html_listado = (FIXTURES / "yapo_listado.html").read_text(encoding="utf-8")
    html_detalle = (FIXTURES / "yapo_detalle.html").read_text(encoding="utf-8")

    tarjetas = parsear_tarjetas(html_listado, "bienes-raices-alquiler-apartamentos")
    assert tarjetas, "el fixture de listado debe traer tarjetas"

    registros = {tarjeta["adid"]: tarjeta for tarjeta in tarjetas}
    scraper = ScraperYapo()
    cliente = _cliente_mock(html_detalle)
    try:
        scraper._scrapear_detalles(_args(max_detalles=1), cliente, tmp_path, registros)
    finally:
        cliente.close()

    registro = next(iter(registros.values()))
    detalle = parsear_detalle(html_detalle)
    # el merge conserva la tarjeta y la enriquece con campos del detalle
    assert registro["region"] == detalle["region"]
    assert registro["m2_construida"] == detalle["m2_construida"]
    assert registro["descripcion"] == detalle["descripcion"]
    # los campos que el detalle trae como None no pisan los del listado
    assert "url_origen" in registro


def test_reparsear_yapo_regenera_parquet(tmp_path):
    """El --reparsear compartido re-parsea el HTML de listado de Yapo."""
    scraper = ScraperYapo()
    scraper.directorio_raw = tmp_path
    run = "20260807_120000"
    html_dir = tmp_path / run / "html"
    html_dir.mkdir(parents=True)
    html = (FIXTURES / "yapo_listado.html").read_text(encoding="utf-8")
    slug = "bienes-raices-alquiler-apartamentos"
    with gzip.open(
        html_dir / f"listado_{slug}_p1.html.gz", "wt", encoding="utf-8"
    ) as f:
        f.write(html)

    scraper.reparsear(run)

    corridas = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    df = pd.read_parquet(tmp_path / corridas[-1] / "propiedades.parquet")
    assert len(df) == 30
    assert str(df["fecha_scraping"].iloc[0].date()) == "2026-08-07"
