# propiedades-cl-ds

Estimación del precio justo de propiedades en el mercado inmobiliario chileno,
detección de publicaciones sub/sobrevaloradas y recomendación de propiedades
similares, a partir de datos scrapeados de portales públicos.

> 🚧 Proyecto en desarrollo — las secciones 5 a 8 se completarán a medida que avancen las fases.

## 1. Problema

En Chile, el precio de publicación de una propiedad no refleja necesariamente su
valor de mercado: los portales mezclan precios en UF y CLP, reportan m² útiles y
totales sin criterio consistente, y no existe una referencia accesible para saber
si una publicación está cara o barata frente a propiedades comparables.

Este proyecto construye un pipeline de datos de extremo a extremo que:

- **Estima el precio justo** de una propiedad a partir de sus características.
- **Detecta sub/sobrevaloración**, definida como el residuo (precio real − precio predicho).
- **Recomienda propiedades similares** a una propiedad dada.

## 2. Origen de los datos

Datos públicos scrapeados con httpx de portales inmobiliarios chilenos
(server-rendered; Playwright disponible como fallback ante anti-bot):

| Fuente | Estado |
| --- | --- |
| Yapo Propiedades | Primera fuente (Fase 1) |
| Portal Inmobiliario | Segunda fuente (Fase 2) |
| TOCTOC | Tercera fuente (Fase 2) |

El scraping corre de forma manual/local (los free tiers de hosting no soportan
scraping de larga duración). Los snapshots crudos se guardan en `data/raw/`
(Parquet) y nunca se editan a mano.

Entidad principal (`properties`): tipo de operación (venta/arriendo), tipo de
propiedad, precio (valor + moneda), m² útiles/totales, gastos comunes,
dormitorios, baños, estacionamientos, bodega, comuna, región, antigüedad,
descripción, y fechas de publicación y scraping. Sin latitud/longitud en la BD
por ahora: se usa `comuna` como proxy geográfico (ver Limitaciones); las
coordenadas que Yapo expone se guardan igual en el parquet crudo.

## 3. Arquitectura

```
Portales (Yapo / Portal Inmobiliario / TOCTOC)
        │  httpx (manual/local)
        ▼
data/raw/ (HTML.gz + Parquet) ──► ETL ──► Supabase (PostgreSQL + PostGIS)
                                      │
                        src/features/ → models/ (LightGBM/XGBoost, offline)
                                      │
                                 api/ (FastAPI → Render)
                                      │
                                 app/ (Streamlit → Streamlit Cloud)
```

- **Lenguaje:** Python 3.11+
- **API / frontend:** FastAPI + Streamlit (migración futura a React + TypeScript)
- **Base de datos:** PostgreSQL + PostGIS gestionado vía Supabase
- **Modelos:** LightGBM / XGBoost (entrenamiento offline, modelo serializado servido por la API)
- **Deploy:** Render free tier (API) + Streamlit Community Cloud (frontend)

## 4. Limpieza de datos

Implementado en `src/etl/` (funciones puras DataFrame → DataFrame, testeadas
sin BD). Reglas actuales:

- **Precios UF → CLP** (`uf.py`): serie diaria `F073.UFF.PRE.Z.D` del Banco
  Central vía `bcchapi`; cada aviso se convierte con la UF de su
  `fecha_publicacion` (fallback: `fecha_scraping`; si el día exacto no tiene
  valor, el día anterior más cercano). Resultado en `precio_clp_normalizado`.
  Los precios implausibles (sobre el tope de su moneda: 500.000 UF /
  10.000M CLP) se anulan: son errores del anunciante, ej. un monto CLP
  tipeado con moneda UF.
- **m² útiles vs. totales** (`limpieza.py`): como las fuentes los reportan de
  forma inconsistente, se usa fallback en cadena (supuesto del MVP):
  `m2_util := m2_construida (detalle) → m2_tarjeta`;
  `m2_total := m2_totales → m2_construida → m2_tarjeta`.
  Los valores implausibles (> 100.000 m²: errores de digitación del
  anunciante, ej. m² multiplicado por 1000) se anulan.
- **Antigüedad**: `antiguedad_anios := año(fecha_scraping) − anio_construccion`
  (mínimo 0).
- **Deduplicación y trazabilidad**: un aviso por `(fuente, url_origen)`
  (constraint UNIQUE); el upsert (`ON CONFLICT DO UPDATE`) actualiza el aviso
  existente con la versión más reciente scrapeada.

## 5. Ingeniería de variables

🚧 *En desarrollo.* Variables planeadas:

- `precio_clp_normalizado` y precio por m².
- Antigüedad derivada de la fecha de publicación.
- Variables geográficas por `comuna` (distancia a metro y similares quedan para cuando se incorpore geocodificación).

## 6. Modelado

🚧 *En desarrollo.* Enfoque:

- Baseline con scikit-learn; modelos finales LightGBM / XGBoost (datos tabulares, dataset pequeño-mediano).
- Interpretabilidad con SHAP.
- Entrenamiento offline y serialización; la API carga el modelo y no reentrena por request.

## 7. Métricas

🚧 *Pendiente.* Se reportarán MAE, RMSE y MAPE del modelo de valoración, con
validación cruzada y, si el volumen lo permite, separación temporal
(entrenar con publicaciones antiguas, evaluar con recientes).

## 8. Resultados

🚧 *Pendiente de las fases de modelado.*

## 9. Limitaciones

- Los precios son de **publicación** (oferta), no de transacción: existe un sesgo respecto al valor de cierre real.
- Sin coordenadas geográficas en el MVP; la ubicación se aproxima por `comuna`, lo que pierde granularidad intra-comuna.
- Los m² útiles/totales se normalizan con supuestos, dada la inconsistencia entre fuentes.
- El scraping es frágil ante cambios de HTML o medidas anti-scraping de los portales.
- Volumen inicial pequeño (miles de registros), lo que acota la complejidad de los modelos.

## 10. Próximos pasos

- [x] Fase 1: scraper de Yapo Propiedades + ETL inicial a Supabase
- [x] Scraper de Portal Inmobiliario (avisos individuales)
- [x] Scraper de TOCTOC (propiedades usadas, vía API interna)
- [ ] EDA en `notebooks/` y modelo baseline
- [ ] API de valoración y frontend Streamlit
- [ ] Geocodificación (Nominatim/OSM) para granularidad geográfica fina
- [ ] Fase 5: orquestación de scrapers con GitHub Actions, reentrenamiento automático y migración a React + TypeScript

## Cómo correrlo

### Requisitos

- Python 3.11+
- Git

### Setup local

```bash
# 1. Clonar el repo
git clone https://github.com/JavierSaldiasA/propiedades-cl-ds.git
cd propiedades-cl-ds

# 2. Crear y activar el entorno virtual
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux/Mac:
source .venv/bin/activate

# 3. Instalar dependencias (incluye herramientas de desarrollo)
pip install -r requirements-dev.txt

# 4. (Opcional) Navegador de fallback para el scraper — solo si httpx
#    llegara a ser bloqueado por anti-bot
playwright install chromium

# 5. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu connection string de Supabase
```

### Uso

```bash
# Scraper de Yapo (manual/local) — scrapea las 4 categorías principales
# (venta/arriendo × casas/deptos) y guarda en data/raw/yapo/<run_id>/
python -m src.scraping.yapo --max-paginas 5 --max-detalles 100 --delay 2.0

# Scraper de Portal Inmobiliario — scrapea las 4 categorías en la sección
# "propiedades-usadas" (solo avisos individuales) y guarda en
# data/raw/portal_inmobiliario/<run_id>/ con las mismas columnas que Yapo
python -m src.scraping.portal_inmobiliario --max-paginas 5 --max-detalles 100 --delay 2.0

# Scraper de TOCTOC — usa su API interna de búsqueda (solo propiedades
# usadas) y descarga la ficha de cada aviso; guarda en
# data/raw/toctoc/<run_id>/ con las mismas columnas que los otros
python -m src.scraping.toctoc --max-paginas 5 --max-detalles 100 --delay 2.0

# Re-parsea los snapshots de una corrida anterior sin tocar la red (útil
# si el parser gana campos nuevos, como las superficies de TOCTOC)
python -m src.scraping.toctoc --reparsear 20260825_182426

# Opciones (los tres): --categorias <slugs>  --max-paginas N  --max-detalles N (0 las omite)  --delay SEG

# ETL a Supabase (requiere .env con URL_DATABASE y credenciales BCCH)
python -m src.etl.cargar --crear-schema            # primera vez: crea la tabla
python -m src.etl.cargar                           # última corrida de cada fuente
python -m src.etl.cargar --fuente toctoc
python -m src.etl.cargar --fuente yapo --run-id 20260807_104024  # corrida específica

# API y frontend: 🚧 en desarrollo. Cuando existan, se correrán así:
# uvicorn api.main:app --reload
# streamlit run app/main.py
```

### Desarrollo

```bash
pytest          # tests
ruff check .    # linter + orden de imports
black .         # formato
```
