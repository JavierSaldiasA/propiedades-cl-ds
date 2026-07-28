# propiedades-cl-ds

Estimación del precio justo de propiedades en el mercado inmobiliario chileno,
detección de publicaciones sub/sobrevaloradas y recomendación de propiedades
similares, a partir de datos scrapeados de portales públicos.

> 🚧 Proyecto en desarrollo — las secciones 4 a 8 se completarán a medida que avancen las fases.

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

Datos públicos scrapeados con Playwright de portales inmobiliarios chilenos:

| Fuente | Estado |
| --- | --- |
| Yapo Propiedades | Primera fuente (Fase 1) |
| Portal Inmobiliario | Pendiente |
| TOCTOC | Pendiente |

El scraping corre de forma manual/local (los free tiers de hosting no soportan
scraping de larga duración). Los snapshots crudos se guardan en `data/raw/`
(Parquet) y nunca se editan a mano.

Entidad principal (`properties`): tipo de operación (venta/arriendo), tipo de
propiedad, precio (valor + moneda), m² útiles/totales, dormitorios, baños,
estacionamientos, bodega, comuna, región, antigüedad, descripción, y fechas de
publicación y scraping. Sin latitud/longitud en el MVP: se usa `comuna` como
proxy geográfico (ver Limitaciones).

## 3. Arquitectura

```
Portales (Yapo / Portal Inmobiliario / TOCTOC)
        │  Playwright (manual/local)
        ▼
data/raw/ (Parquet) ──► ETL ──► Supabase (PostgreSQL + PostGIS)
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

🚧 *En desarrollo.* Alcance planeado:

- Normalización de precios UF ↔ CLP para comparar venta y arriendo.
- Normalización de m² útiles vs. totales (las fuentes los reportan de forma inconsistente).
- Deduplicación de publicaciones y trazabilidad por `fuente` y `url_origen`.

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

- [ ] Fase 1: scraper de Yapo Propiedades + ETL inicial a Supabase
- [ ] Scrapers de Portal Inmobiliario y TOCTOC
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

# 4. Descargar el navegador para el scraper
playwright install chromium

# 5. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu connection string de Supabase
```

### Uso

🚧 Los componentes ejecutables (scraper, API, app) están en desarrollo.
Cuando existan, se correrán así:

```bash
# Scraper (manual/local)
python -m src.scraping.yapo

# API (desarrollo)
uvicorn api.main:app --reload

# Frontend
streamlit run app/main.py
```

### Desarrollo

```bash
pytest          # tests
ruff check .    # linter + orden de imports
black .         # formato
```
