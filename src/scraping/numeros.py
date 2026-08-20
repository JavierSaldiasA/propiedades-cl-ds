"""Helpers de parsing de números y precios en formato chileno (es-CL).

En formato es-CL el punto es separador de miles y la coma es decimal:
"1.500.000" -> 1500000.0, "7.000,00" -> 7000.0
"""

from __future__ import annotations

import re


def parsear_numero_cl(texto: str | None) -> float | None:
    """Convierte un número en formato es-CL a float. Devuelve None si no se puede."""
    if not texto:
        return None
    limpio = texto.strip().replace("\xa0", "").replace(" ", "")
    if not limpio:
        return None
    if "," in limpio:
        limpio = limpio.replace(".", "").replace(",", ".")
    else:
        limpio = limpio.replace(".", "")
    try:
        return float(limpio)
    except ValueError:
        return None


def parsear_m2(texto: str | None) -> float | None:
    """Extrae un m² de un texto con separadores es-CL o US mezclados.

    Portal Inmobiliario reporta los m² en formatos inconsistentes según el
    componente: coma decimal es-CL ("37,54"), punto de miles es-CL
    ("5.000"), punto decimal US ("63.1") o entero plano ("163"). Regla para
    el punto: si tiene exactamente 3 dígitos tras él (o hay más de un
    punto) se trata como separador de miles; con 1-2 dígitos, como decimal
    US. Yapo trae el mismo problema en su página de detalle.
    """
    if not texto:
        return None
    coincidencia = re.search(r"[\d.,]+", texto)
    if not coincidencia:
        return None
    numero = coincidencia.group()
    if "," in numero or numero.count(".") > 1:
        return parsear_numero_cl(numero)
    if re.fullmatch(r"\d+\.\d{3}", numero):
        return parsear_numero_cl(numero)
    try:
        return float(numero)
    except ValueError:
        return None


def parsear_precio_texto(texto: str | None) -> tuple[float | None, str | None]:
    """Extrae (valor, moneda) de un precio tal como aparece en Yapo.

    "$1.500.000" -> (1500000.0, "CLP")
    "UF7.000,00" -> (7000.0, "UF")
    Vacío o irreconocible -> (None, None)
    """
    if not texto:
        return (None, None)
    limpio = texto.strip()
    if limpio.upper().startswith("UF"):
        moneda, numero = "UF", limpio[2:]
    elif limpio.startswith("$"):
        moneda, numero = "CLP", limpio[1:]
    else:
        return (None, None)
    return (parsear_numero_cl(numero), moneda)
