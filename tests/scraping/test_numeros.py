"""Tests de src/scraping/numeros.py (formato es-CL: punto=miles, coma=decimal)."""

import pytest

from src.scraping.numeros import parsear_numero_cl, parsear_precio_texto


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("1.500.000", 1500000.0),
        ("7.000,00", 7000.0),
        ("85000", 85000.0),
        ("55,5", 55.5),
        ("57", 57.0),
        ("-3", -3.0),
    ],
)
def test_parsear_numero_cl(texto, esperado):
    assert parsear_numero_cl(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "   ", "abc"])
def test_parsear_numero_cl_invalido(texto):
    assert parsear_numero_cl(texto) is None


@pytest.mark.parametrize(
    "texto, valor, moneda",
    [
        ("$1.500.000", 1500000.0, "CLP"),
        ("$450.000", 450000.0, "CLP"),
        ("UF7.000,00", 7000.0, "UF"),
        ("UF40,00", 40.0, "UF"),
        ("uf42,00", 42.0, "UF"),
    ],
)
def test_parsear_precio_texto(texto, valor, moneda):
    assert parsear_precio_texto(texto) == (valor, moneda)


@pytest.mark.parametrize("texto", [None, "", "Consultar", "123"])
def test_parsear_precio_texto_sin_moneda(texto):
    assert parsear_precio_texto(texto) == (None, None)
