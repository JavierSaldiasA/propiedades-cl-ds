"""Tests de src/scraping/numeros.py (formato es-CL: punto=miles, coma=decimal)."""

import pytest

from src.scraping.numeros import (
    parsear_m2,
    parsear_numero_cl,
    parsear_precio_texto,
)


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


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("163 m²", 163.0),  # entero plano
        ("163 m² útiles", 163.0),
        ("37,54 m²", 37.54),  # coma decimal es-CL
        ("5.000 m² totales", 5000.0),  # punto de miles es-CL (3 dígitos)
        ("25.000 m²", 25000.0),
        ("63.1", 63.1),  # punto decimal US (1 dígito)
        ("80.50", 80.5),  # punto decimal US (2 dígitos)
        ("1.234.567 m²", 1234567.0),  # grupos de miles múltiples
    ],
)
def test_parsear_m2(texto, esperado):
    assert parsear_m2(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "m²", "superficie"])
def test_parsear_m2_invalido(texto):
    assert parsear_m2(texto) is None
