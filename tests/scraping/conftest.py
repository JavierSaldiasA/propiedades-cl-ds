"""Fixtures compartidos: HTML real descargado de Yapo el 2026-08-07.

- yapo_listado.html: página 1 de /bienes-raices-alquiler-apartamentos (30 tarjetas)
- yapo_listado_mixto.html: listado genérico /searchresult/bienes-raices
  (mezcla subcategorías: sirve para probar el filtrado por categoría)
- yapo_detalle.html: detalle del aviso 32632138 (depto. arriendo, Santiago)
"""

from pathlib import Path

import pytest

DIRECTORIO_FIXTURES = Path(__file__).parent / "fixtures"


def _leer_fixture(nombre: str) -> str:
    return (DIRECTORIO_FIXTURES / nombre).read_text(encoding="utf-8")


@pytest.fixture
def html_listado() -> str:
    return _leer_fixture("yapo_listado.html")


@pytest.fixture
def html_listado_mixto() -> str:
    return _leer_fixture("yapo_listado_mixto.html")


@pytest.fixture
def html_detalle() -> str:
    return _leer_fixture("yapo_detalle.html")
