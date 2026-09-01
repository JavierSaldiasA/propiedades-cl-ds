"""Lectura de la tabla `properties` de Supabase para exploración y EDA.

Solo lectura (SELECT *): nada de esto escribe en la base de datos. Es el
punto de entrada de los notebooks de `notebooks/` cuando necesitan datos
normalizados (ya pasados por el ETL), en lugar de los parquet de scraping.
"""

from __future__ import annotations

import pandas as pd
import psycopg

from src.config import obtener_configuraciones

FECHA_COLUMNAS = ("fecha_publicacion", "fecha_scraping")
# Los NUMERIC de Postgres llegan como str; se convierten a float64.
NUMERICAS = (
    "precio_valor",
    "precio_clp_normalizado",
    "m2_util",
    "m2_total",
    "gastos_comunes",
)
BOOLEANAS = ("bodega",)

# Consulta parametrizada: `tipo_operacion` se pasa como placeholder (%s), nunca
# interpolado en el string, para evitar inyección SQL.
SQL_PROPIEDADES = (
    "SELECT * FROM properties WHERE tipo_operacion = %s "
    "ORDER BY fuente, fecha_scraping"
)


def cargar_properties(tipo_operacion: str) -> pd.DataFrame:
    """Devuelve todas las filas de `public.properties` como DataFrame.

    Los fechas se convierten a datetime, las columnas NUMERIC a float64 y las
    booleanas a bool. Las filas se ordenan por fuente y fecha de scraping para
    una lectura estable.
    """
    url_database = obtener_configuraciones().url_database
    with psycopg.connect(url_database) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(SQL_PROPIEDADES, (tipo_operacion,))
            columnas = [d[0] for d in cursor.description]
            filas = cursor.fetchall()
    df = pd.DataFrame(filas, columns=columnas)
    for columna in FECHA_COLUMNAS:
        if columna in df.columns:
            df[columna] = pd.to_datetime(df[columna])
    for columna in NUMERICAS:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
    for columna in BOOLEANAS:
        if columna in df.columns:
            df[columna] = df[columna].astype("boolean")
    return df
