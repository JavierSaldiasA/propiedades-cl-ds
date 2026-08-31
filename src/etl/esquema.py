"""Espec única del esquema de la tabla `properties` y generación del DDL.

Centraliza el contrato de columnas de la tabla `properties` con sus tipos SQL
para que el Docker/DDL (`docker/db/schema.sql`), el DataFrame del ETL y el
scraping no se desincronicen a mano. El DDL se genera desde esta spec.

Las columnas que entran a la tabla son un subconjunto de las crudas de
scraping (ver src/scraping/base.COLUMNAS) más las derivadas del ETL
(`precio_clp_normalizado`, `m2_util`, `m2_total`, `antiguedad_anios`,
`fuente`).
"""

from __future__ import annotations

from pathlib import Path

# Columnas de la tabla `properties`, en orden, sin `id` (BIGSERIAL).
COLUMNAS_PROPERTIES = [
    "fuente",
    "url_origen",
    "tipo_operacion",
    "tipo_propiedad",
    "precio_valor",
    "precio_moneda",
    "precio_clp_normalizado",
    "m2_util",
    "m2_total",
    "gastos_comunes",
    "dormitorios",
    "banos",
    "estacionamientos",
    "bodega",
    "comuna",
    "region",
    "antiguedad_anios",
    "descripcion",
    "fecha_publicacion",
    "fecha_scraping",
]

# Columna -> tipo SQL declarado en el CREATE TABLE.
TIPOS_SQL = {
    "fuente": "TEXT NOT NULL",
    "url_origen": "TEXT NOT NULL",
    "tipo_operacion": "TEXT NOT NULL",
    "tipo_propiedad": "TEXT",
    "precio_valor": "NUMERIC(14, 2)",
    "precio_moneda": "TEXT",
    "precio_clp_normalizado": "NUMERIC(14, 2)",
    "m2_util": "NUMERIC(8, 2)",
    "m2_total": "NUMERIC(8, 2)",
    "gastos_comunes": "NUMERIC(14, 2)",
    "dormitorios": "SMALLINT",
    "banos": "SMALLINT",
    "estacionamientos": "SMALLINT",
    "bodega": "BOOLEAN",
    "comuna": "TEXT",
    "region": "TEXT",
    "antiguedad_anios": "SMALLINT",
    "descripcion": "TEXT",
    "fecha_publicacion": "DATE",
    "fecha_scraping": "DATE NOT NULL",
}

CHECK_FUENTE = "CHECK (fuente IN ('portal_inmobiliario', 'yapo', 'toctoc'))"
CHECK_OPERACION = "CHECK (tipo_operacion IN ('venta', 'arriendo'))"
CHECK_MONEDA = "CHECK (precio_moneda IN ('UF', 'CLP'))"

# Columnas de la constraint UNIQUE de deduplicación (fuente + URL origen).
COLUMNAS_CONFLICTO = ("fuente", "url_origen")


def generar_schema() -> str:
    """Devuelve el DDL idempotente de la tabla `properties`."""
    lineas = ["-- Schema inicial de la base de datos (Supabase Postgres).", ""]
    lineas.append("CREATE TABLE IF NOT EXISTS properties (")
    lineas.append("    id BIGSERIAL PRIMARY KEY,")
    for columna in COLUMNAS_PROPERTIES:
        tipo = TIPOS_SQL[columna]
        checks = []
        if columna == "fuente":
            checks.append(CHECK_FUENTE)
        elif columna == "tipo_operacion":
            checks.append(CHECK_OPERACION)
        elif columna == "precio_moneda":
            checks.append(CHECK_MONEDA)
        definicion = tipo
        if checks:
            definicion = f"{definicion} {', '.join(checks)}"
        lineas.append(f"    {columna} {definicion},")
    cols_conflicto = ", ".join(COLUMNAS_CONFLICTO)
    lineas.append("    -- Trazabilidad y deduplicación: un aviso por fuente+URL")
    lineas.append(f"    CONSTRAINT uq_properties_fuente_url UNIQUE ({cols_conflicto})")
    lineas.append(");")
    lineas.append("")
    lineas.append(
        "CREATE INDEX IF NOT EXISTS idx_properties_comuna ON properties (comuna);"
    )
    lineas.append(
        "CREATE INDEX IF NOT EXISTS idx_properties_tipo_operacion "
        "ON properties (tipo_operacion);"
    )
    lineas.append("")
    return "\n".join(lineas)


# Ruta canónica del schema aplicable a la BD.
RUTA_SCHEMA = Path("docker/db/schema.sql")
