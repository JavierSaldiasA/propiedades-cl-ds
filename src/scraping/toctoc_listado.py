"""Parsing de las respuestas del API de búsqueda de TOCTOC (GetProps).

Funciones puras: reciben el dict JSON de GetProps y devuelven dicts, sin
tocar red ni disco.

GetProps devuelve cada propiedad como un ARREGLO posicional de ~45 campos
(formato compacto del API de mapa). Solo se extraen las posiciones
necesarias para descubrir avisos; los datos completos y confiables vienen
de la ficha (toctoc_ficha.py).

Posiciones verificadas contra el API real el 2026-08-24 (precios, id,
URL, comuna, fecha) y el 2026-08-25 contra 99 fichas enriquecidas
(superficies, dormitorios y baños):
- [1] id de la propiedad, [2] longitud, [3] latitud, [7] comuna
- [14] fecha de publicación ("dd-mm-yyyy 0:00:00")
- [22] precio de publicación (moneda real del aviso), [24] su conversión
  a la otra moneda
- [39] título, [40] URL de la ficha
- [4] baños, [8] dormitorios (pares [x]/[x+1] duplicados; en usados ambos
  valores coinciden): 92-96/96 coincidencias exactas contra fichas
- [31] superficie total (terreno si hay), [33] superficie útil

Trampas conocidas:
- El POST acepta tipoPropiedad pero NO filtra: el tipo se infiere del
  patrón de la URL (/casa/ o /departamento/).
- La moneda de [22] no se declara: se infiere comparando con la conversión
  [24] (mayor => la publicación estaba en UF). La ficha confirma la
  moneda con su propia aritmética.
- Las búsquedas mezclan casas y departamentos: la categoría se asigna por
  URL y el orquestador filtra.
"""

from __future__ import annotations

from datetime import datetime

# (tipo_operacion, tipo_propiedad) -> slug de categoría
CATEGORIAS_PRINCIPALES: dict[tuple[str, str], str] = {
    ("venta", "casa"): "venta-casa",
    ("venta", "departamento"): "venta-departamento",
    ("arriendo", "casa"): "arriendo-casa",
    ("arriendo", "departamento"): "arriendo-departamento",
}


def _inferir_tipos(url: str) -> tuple[str | None, str | None]:
    """(tipo_operacion, tipo_propiedad) desde el patrón de la URL.

    Ej: /propiedades/compraparticularsr/casa/maipu/... -> (venta, casa)
        /propiedades/arriendocorredorasr/departamento/... -> (arriendo, departamento)
    """
    operacion = None
    if "/compra" in url:
        operacion = "venta"
    elif "/arriendo" in url:
        operacion = "arriendo"
    tipo = None
    if "/casa/" in url:
        tipo = "casa"
    elif "/departamento/" in url:
        tipo = "departamento"
    return (operacion, tipo)


def _parsear_fecha(texto: str | None) -> datetime | None:
    """ "25-06-2026 0:00:00" -> date. None si no calza."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.split()[0], "%d-%m-%Y")
    except ValueError:
        return None


def _formatear_precio(valor: float | None, moneda: str | None) -> str | None:
    if valor is None or moneda is None:
        return None
    if float(valor).is_integer():
        texto = f"{int(valor):,}".replace(",", ".")
    else:
        texto = str(valor).replace(".", ",")
    simbolo = {"UF": "UF", "CLP": "$"}.get(moneda, moneda)
    return f"{simbolo} {texto}"


def _elegir_precio(
    precio_publicacion: float, precio_conversion: float
) -> tuple[float | None, str | None]:
    """(valor, moneda) del arreglo posicional.

    [22] es el precio de publicación (en la moneda real del aviso) y [24]
    su conversión a la otra moneda: la moneda se infiere comparándolos —
    la conversión es MAYOR que el original si este estaba en UF (multiplica
    por ~40.864) y menor si estaba en CLP (divide). Verificado en 1.020
    avisos reales: la tasa implícita siempre calza con la UF del día.
    """
    if precio_publicacion <= 0:
        return (None, None)
    if precio_conversion > 0:
        moneda = "UF" if precio_conversion > precio_publicacion else "CLP"
        return (precio_publicacion, moneda)
    # sin conversión disponible: heurística de magnitud
    return (precio_publicacion, "CLP" if precio_publicacion >= 100_000 else "UF")


def _parsear_propiedad(propiedad: list) -> dict | None:
    """Parsea un arreglo posicional; None si no es de una categoría conocida."""
    url = propiedad[40]
    tipo_operacion, tipo_propiedad = _inferir_tipos(url)
    if not tipo_operacion or not tipo_propiedad:
        return None
    precio_valor, precio_moneda = _elegir_precio(
        float(propiedad[22] or 0), float(propiedad[24] or 0)
    )
    return {
        "adid": str(propiedad[1]),
        "url_origen": url,
        "categoria_slug": CATEGORIAS_PRINCIPALES[(tipo_operacion, tipo_propiedad)],
        "tipo_operacion": tipo_operacion,
        "tipo_propiedad": tipo_propiedad,
        "titulo": propiedad[39] or None,
        "precio_texto": _formatear_precio(precio_valor, precio_moneda),
        "precio_valor": precio_valor,
        "precio_moneda": precio_moneda,
        "comuna": propiedad[7] or None,
        "region": None,  # no viene en el listado; la ficha la trae
        "m2_construida": _positivo(propiedad[33]),  # superficie útil
        "m2_totales": _positivo(propiedad[31]),  # total (terreno si hay)
        "dormitorios": _entero_positivo(propiedad[8]),
        "banos": _entero_positivo(propiedad[4]),
        "latitud": propiedad[3] if propiedad[3] else None,
        "longitud": propiedad[2] if propiedad[2] else None,
        "fecha_publicacion": _parsear_fecha(propiedad[14]),
    }


def _positivo(valor) -> float | None:
    """0.0 (sin dato en el arreglo) -> None."""
    numero = float(valor) if valor else 0.0
    return numero if numero > 0 else None


def _entero_positivo(valor) -> int | None:
    numero = _positivo(valor)
    return int(numero) if numero is not None else None


def parsear_listado(respuesta: dict) -> list[dict]:
    """Extrae los avisos de una página de resultados de GetProps."""
    resultados = respuesta.get("resultados") or {}
    propiedades = resultados.get("Propiedades") or []
    registros = []
    for propiedad in propiedades:
        if not isinstance(propiedad, list) or len(propiedad) < 41:
            continue
        registro = _parsear_propiedad(propiedad)
        if registro:
            registros.append(registro)
    return registros


def parsear_total(respuesta: dict) -> int | None:
    """Total de avisos de la búsqueda."""
    total = (respuesta.get("resultados") or {}).get("Total")
    return int(total) if isinstance(total, (int, float)) else None


def obtener_pagina(respuesta: dict) -> int:
    """Número de página que devolvió la búsqueda (1-index)."""
    pagina = (respuesta.get("resultados") or {}).get("Pagina")
    return int(pagina) if isinstance(pagina, (int, float)) else 1


def hay_siguiente_pagina(respuesta: dict) -> bool:
    """True si quedan páginas por pedir según el total y el tamaño de página."""
    resultados = respuesta.get("resultados") or {}
    total = resultados.get("Total")
    por_pagina = resultados.get("TotalPorPagina")
    pagina = resultados.get("Pagina", 1)
    if not isinstance(total, (int, float)):
        return False
    if not isinstance(por_pagina, (int, float)) or por_pagina <= 0:
        return False
    return pagina * por_pagina < total
