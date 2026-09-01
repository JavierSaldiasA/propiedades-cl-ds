"""Serie diaria de la UF (Banco Central) y conversión UF→CLP.

Fuente oficial vía bcchapi:
Serie F073.UFF.PRE.Z.D. La conversión usa la UF de la fecha de publicación del
aviso (fallback: fecha de scraping); si el día exacto no tiene valor se
usa el día anterior más cercano disponible (asof).
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Hashable

import pandas as pd

logger = logging.getLogger(__name__)

SERIE_UF = "F073.UFF.PRE.Z.D"
REINTENTOS = 3
ESPERA_REINTENTO = 2.0

_CACHE: dict[tuple[Hashable, ...], pd.Series] = {}


def _descargar_serie_bcch(
    desde: str | date, hasta: str | date, usuario: str, password: str
) -> pd.Series:
    import bcchapi  # import perezoso: los tests no lo necesitan

    siete = bcchapi.Siete(usr=usuario, pwd=password)
    df = siete.cuadro(series=[SERIE_UF], desde=str(desde), hasta=str(hasta))
    serie = df[SERIE_UF].sort_index()
    serie.index = pd.to_datetime(serie.index)
    return serie


def _descargar_con_reintentos(
    desde: str | date, hasta: str | date, usuario: str, password: str
) -> pd.Series:
    """Descarga la serie, reintentando ante errores transitorios (red/API)."""
    for intento in range(1, REINTENTOS + 1):
        try:
            return _descargar_serie_bcch(desde, hasta, usuario, password)
        except Exception as ex:
            if intento == REINTENTOS:
                raise
            logger.warning(
                "Error descargando serie UF (intento %d/%d): %s",
                intento,
                REINTENTOS,
                ex,
            )
            time.sleep(ESPERA_REINTENTO * intento)
    raise AssertionError("loop inalcanzable")


def _clave_serie(
    desde: str | date, hasta: str | date, usuario: str, password: str
) -> tuple[Hashable, ...]:
    return (str(desde), str(hasta), usuario, password)


def obtener_serie_uf(
    desde: str | date,
    hasta: str | date,
    usuario: str | None = None,
    password: str | None = None,
) -> pd.Series:
    """Descarga la serie diaria de la UF entre `desde` y `hasta`.

    Devuelve una pd.Series fecha -> valor (CLP por UF), ordenada por fecha.
    Las credenciales se toman de la configuración si no se pasan explícitas.
    """
    if usuario is None or password is None:
        from src.config import obtener_configuraciones

        config = obtener_configuraciones()
        usuario = usuario if usuario is not None else config.usuario_bcch
        password = password if password is not None else config.password_bcch
    clave = _clave_serie(desde, hasta, usuario, password)
    if clave in _CACHE:
        logger.info("Serie UF servida desde caché (%s -> %s)", desde, hasta)
        return _CACHE[clave]
    serie = _descargar_con_reintentos(desde, hasta, usuario, password)
    _CACHE[clave] = serie
    return serie


def valor_uf_en_fecha(serie_uf: pd.Series, fecha: Any) -> float | None:
    """Valor de la UF en `fecha`, o el día anterior más cercano disponible.

    None si la fecha es nula, la serie está vacía o la fecha es anterior
    al inicio de la serie.
    """
    if fecha is None or pd.isna(fecha) or serie_uf.empty:
        return None
    valor = serie_uf.asof(pd.Timestamp(fecha))
    return None if pd.isna(valor) else float(valor)


def convertir_a_clp(
    valor: Any, moneda: Any, fecha: Any, serie_uf: pd.Series
) -> float | None:
    """Convierte un precio a CLP.

    - CLP pasa directo.
    - UF se multiplica por la UF de `fecha` (ver valor_uf_en_fecha).
    - Moneda desconocida o datos faltantes -> None.
    """
    if valor is None or pd.isna(valor):
        return None
    if moneda == "CLP":
        return float(valor)
    if moneda == "UF":
        uf = valor_uf_en_fecha(serie_uf, fecha)
        return float(valor) * uf if uf is not None else None
    return None
