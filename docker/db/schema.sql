-- Schema inicial de la base de datos (Supabase Postgres).

CREATE TABLE IF NOT EXISTS properties (
    id BIGSERIAL PRIMARY KEY,
    fuente TEXT NOT NULL CHECK (fuente IN ('portal_inmobiliario', 'yapo', 'toctoc')),
    url_origen TEXT NOT NULL,
    tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('venta', 'arriendo')),
    tipo_propiedad TEXT,
    precio_valor NUMERIC(14, 2),
    precio_moneda TEXT CHECK (precio_moneda IN ('UF', 'CLP')),
    precio_clp_normalizado NUMERIC(14, 2),
    m2_util NUMERIC(8, 2),
    m2_total NUMERIC(8, 2),
    dormitorios SMALLINT,
    banos SMALLINT,
    estacionamientos SMALLINT,
    bodega BOOLEAN,
    comuna TEXT,
    region TEXT,
    antiguedad_anios SMALLINT,
    descripcion TEXT,
    fecha_publicacion DATE,
    fecha_scraping DATE NOT NULL,
    -- Trazabilidad y deduplicación: un aviso por fuente+URL
    CONSTRAINT uq_properties_fuente_url UNIQUE (fuente, url_origen)
);

CREATE INDEX IF NOT EXISTS idx_properties_comuna ON properties (comuna);
CREATE INDEX IF NOT EXISTS idx_properties_tipo_operacion ON properties (tipo_operacion);
