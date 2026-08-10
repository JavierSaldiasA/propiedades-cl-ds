"""Helpers de parsing de números y precios en formato chileno (es-CL).

En formato es-CL el punto es separador de miles y la coma es decimal:
"1.500.000" -> 1500000.0, "7.000,00" -> 7000.0
"""

from __future__ import annotations


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
