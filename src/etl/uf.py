"""Serie diaria de la UF (Banco Central) y conversión UF→CLP.

Fuente oficial vía bcchapi:
Serie F073.UFF.PRE.Z.D. La conversión usa la UF de la fecha de publicación del
aviso (fallback: fecha de scraping); si el día exacto no tiene valor se
usa el día anterior más cercano disponible (asof).
"""

from __future__ import annotations

import pandas as pd

SERIE_UF = "F073.UFF.PRE.Z.D"


def obtener_serie_uf(desde, hasta, usuario=None, password=None) -> pd.Series:
    """Descarga la serie diaria de la UF entre `desde` y `hasta`.

    Devuelve una pd.Series fecha -> valor (CLP por UF), ordenada por fecha.
    Las credenciales se toman de la configuración si no se pasan explícitas.
    """
    import bcchapi  # import perezoso: los tests no lo necesitan

    if usuario is None or password is None:
        from src.config import obtener_configuraciones

        config = obtener_configuraciones()
        usuario = usuario if usuario is not None else config.usuario_bcch
        password = password if password is not None else config.password_bcch
    siete = bcchapi.Siete(usr=usuario, pwd=password)
    df = siete.cuadro(series=[SERIE_UF], desde=str(desde), hasta=str(hasta))
    serie = df[SERIE_UF].sort_index()
    serie.index = pd.to_datetime(serie.index)
    return serie


def valor_uf_en_fecha(serie_uf: pd.Series, fecha) -> float | None:
    """Valor de la UF en `fecha`, o el día anterior más cercano disponible.

    None si la fecha es nula, la serie está vacía o la fecha es anterior
    al inicio de la serie.
    """
    if fecha is None or pd.isna(fecha) or serie_uf.empty:
        return None
    valor = serie_uf.asof(pd.Timestamp(fecha))
    return None if pd.isna(valor) else float(valor)


def convertir_a_clp(valor, moneda, fecha, serie_uf: pd.Series) -> float | None:
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
