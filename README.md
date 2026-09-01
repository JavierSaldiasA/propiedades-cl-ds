# propiedades-cl-ds

Estimación del precio justo de propiedades en el mercado inmobiliario chileno,
detección de publicaciones sub/sobrevaloradas y recomendación de propiedades
similares, a partir de datos scrapeados de portales públicos.

> ✓ Proyecto con baseline funcional — las secciones 7 y 8 se completan con la mejora de modelos.

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

Implementado en `src/features/` (funciones puras DataFrame → DataFrame, testeadas
sin BD). Transformaciones que toma la tabla `properties` limpia para dejarla
lista para modelar:

- **Target**: `precio_log = log1p(precio_clp_normalizado)` (cola larga confirmada
  en el EDA). Se descartan avisos sin precio válido (`<= 0` o ausente).
- **Precio por m²**: `precio_por_m2_util` y `precio_por_m2_total` (NA si m² = 0 o falta).
- **Indicadores de nulos**: flag binario `sin_<columna>` para las columnas con
  ausencia informativa (`m2_util`, `m2_total`, `gastos_comunes`,
  `estacionamientos`, `antiguedad_anios`, `bodega`).
- **Imputación** de las numéricas (`m2_util`, `m2_total`, `banos`, `dormitorios`,
  `estacionamientos`, `antiguedad_anios`) con la **mediana por comuna** (el
  efecto geográfico es el más informativo del EDA), con fallback a la mediana
  global si la comuna no tiene datos.
- **Encodings**:
  - `comuna` → **target-mean encoding con smoothing** (promedio ponderado entre
    media local y media global). Las comunas raras (< 20 avisos) se funden en
    `comuna_otra` (su estimación es ruido con tan poca evidencia).
  - `tipo_propiedad` y `fuente` → one-hot.
- **Outliers de precio**: método **IQR sobre el log** del precio (k = 3); se
  aplica al ajustar (fit), no al hacer score, porque con una sola fila el IQR
  degeneraría.
- **Patrón fit/transform sin data leakage**: `calcular_setup(df)` calcula una
  sola vez medianas, encodings y umbrales; `construir_matriz(df, setup)` los
  aplica igual en entrenamiento y en score. El setup se persiste junto al modelo.

Las variables geográficas finas (distancia a metro y similares) quedan para
cuando se incorpore la geocodificación.

## 6. Modelado

Implementado en `src/modelo/`. Pipeline de entrenamiento (`python -m src.modelo.entrenar`),
que lee de Supabase, ajusta el setup global y valida con **CV honesto**:

- **Validación cruzada honesta**: el target-mean encoding de `comuna` se recalcula
  dentro de cada fold (`construir_matrices_fold`), de modo que el target de la
  validación nunca entra en los features con los que se predice. El setup global
  (medianas de imputación, one-hot, umbrales, outliers de precio) se ajusta una
  sola vez sobre todo el dataset y se persiste junto al modelo.
- **Baselines comparados** por fold y agregados (mejor por MAPE): el trivial
  `mediana` (piso que cualquier modelo debe superar), `ridge` (regresión lineal
  regularizada con escalado estandarizado), `RandomForestRegressor` y
  `HistGradientBoostingRegressor`.
- **Winsorización**: las features numéricas se recortan a los percentiles
  1-99 % calculados sobre el dataset (como el resto del setup global). Sin este
  recorte, las colas pesadas de los datos reales (gastos comunes o m² extremos)
  hacen explotar la extrapolación de los modelos lineales.
- **Features excluidas**: `precio_por_m2_util`/`precio_por_m2_total` quedan fuera
  de la matriz porque se derivan del mismo precio que es el target (el modelo
  podría reconstruirlo como una tautología y las métricas dejarían de medir
  capacidad de predicción).
- **Artefacto**: `models/modelo_venta.joblib` y `models/modelo_arriendo.joblib`
  (uno por operación; no se sobrescriben entre sí), con modelo + setup + clip +
  columnas + resultados del CV y los metadatos; la API los carga y hace score sin
  reentrenar.

El baseline es scikit-learn por ahora; la interpretabilidad con SHAP y el salto a
LightGBM/XGBoost quedan para la mejora de modelos.

## 7. Métricas

Reportadas con validación cruzada (KFold, target encoding por fold), en el espacio
del log (donde se entrena) y en CLP (donde se interpreta el error de una valoración):

- **MAE**, **RMSE** y **R²** sobre `log1p(precio)`.
- **MAE CLP**, **RMSE CLP** y **MAPE (%)** sobre los precios (se deshace el log con `expm1`).

Corrida baseline (2026-09-01, 5 folds, semilla 42).

**Venta** (3.328 avisos, mejor modelo: **HistGradientBoosting**):

| Modelo | MAPE | MAE CLP | RMSE CLP | R² (log) |
| --- | --- | --- | --- | --- |
| HistGradientBoosting | **22,9%** ± 1,8 | 114,3M | 222,2M | 0,86 |
| RandomForest | 23,7% ± 1,9 | 116,6M | 223,2M | 0,86 |
| Ridge (lineal escalado) | 32,7% ± 1,4 | 163,6M | 296,8M | 0,76 |
| Mediana (trivial) | 94,0% ± 3,3 | 309,1M | 471,6M | −0,01 |

**Arriendo** (3.321 avisos, mejor modelo: **RandomForest**):

| Modelo | MAPE | MAE CLP | RMSE CLP | R² (log) |
| --- | --- | --- | --- | --- |
| RandomForest | **25,5%** ± 3,3 | 331,4K | 1,05M | 0,85 |
| HistGradientBoosting | 26,9% ± 4,0 | 343,7K | 1,05M | 0,84 |
| Ridge (lineal escalado) | 29,2% ± 1,0 | 400,8K | 1,16M | 0,81 |
| Mediana (trivial) | 60,4% ± 2,6 | 848,8K | 1,91M | −0,06 |

La separación temporal (entrenar con publicaciones antiguas, evaluar con recientes)
queda como mejora cuando el volumen y las fechas de publicación lo permitan.

## 8. Resultados

🚧 *Pendiente de la mejora de modelos.* El baseline sitúa el MAPE de la valoración
en ~23 % (venta) y en ~25 % (arriendo), con el que hoy rinde mejor por operación
(HistGradientBoosting en venta, RandomForest en arriendo); la detección de
sub/sobrevaloración y las recomendaciones de propiedades similares se desencadenan
sobre los residuos de estos modelos.

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
- [x] EDA en `notebooks/`
- [x] Feature engineering en `src/features/`
- [x] Modelo baseline (Fase 4) con CV honesto en `src/modelo/`
- [ ] Mejora de modelos (LightGBM/XGBoost, SHAP, separación temporal)
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
pip install -e ".[dev]"

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

# Entrenamiento del modelo baseline (lee `venta`/`arriendo` de Supabase).
# Evalúa los baselines con CV honesto y guarda el artefacto por operación:
#   models/modelo_venta.joblib / models/modelo_arriendo.joblib
python -m src.modelo.entrenar                              # venta, 5 folds
python -m src.modelo.entrenar --tipo-operacion arriendo --folds 5 --semilla 42

# API y frontend: 🚧 en desarrollo. Cuando existan, se correrán así:
# uvicorn api.main:app --reload
# streamlit run app/main.py

# API en Docker (imagen multi-stage en docker/Dockerfile; requiere .env):
# make docker-up   (Linux) / ./tasks.ps1 docker-up   (Windows)
```

### Desarrollo

Las rutas de datos y config se resuelven desde la raíz del repo (no desde el
directorio de invocación); se puede sobrescribir con `PROPIEDADES_ROOT`.

```bash
./tasks.ps1 ci        # Windows: ruff + black --check + pytest (con coverage)
make ci               # Linux/CI: lo mismo
make install          # o: ./tasks.ps1 install (pip install -e ".[dev]")
make hooks            # o: ./tasks.ps1 hooks (instala los pre-commit git hooks)

# Equivalencias manuales
pytest -q             # tests + reporte de coverage
ruff check src tests  # linter + orden de imports
black src tests       # formato
```

El workflow de CI (`.github/workflows/ci.yml`) corre los mismos checks
(python 3.11 y 3.14). El pre-commit (`ruff`, `black`, hooks útiles) se instala
con `make hooks` / `./tasks.ps1 hooks`.
