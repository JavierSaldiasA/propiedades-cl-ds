"""Configuración y constantes del feature engineering.

Centraliza umbrales y estrategias usadas por `src/features/construir.py` para
que sean fáciles de ajustar y queden documentados. No contiene lógica: solo
valores.
"""

from __future__ import annotations

# Target: modelamos el logaritmo del precio (cola larga confirmada en el EDA).
COLUMNA_PRECIO = "precio_clp_normalizado"
COLUMNA_TARGET = "precio_log"

# Columnas numéricas a imputar, con su estrategia de agrupación. La mediana por
# comuna captura el efecto geográfico (es el feature más informativo del EDA);
# si una comuna no tiene datos se cae a la mediana global (fallback).
NUMERICAS_IMPUTAR = {
    "m2_util": {"grupo": "comuna", "estadistico": "median"},
    "m2_total": {"grupo": "comuna", "estadistico": "median"},
    "banos": {"grupo": "comuna", "estadistico": "median"},
    "dormitorios": {"grupo": "comuna", "estadistico": "median"},
    "estacionamientos": {"grupo": "comuna", "estadistico": "median"},
    "antiguedad_anios": {"grupo": "comuna", "estadistico": "median"},
}

# Columnas con nulos abundantes a las que agregamos un indicador binario
# "sin_<columna>" para que el modelo pueda aprovechar la ausencia de dato
# (patrón estructural ya observado en el EDA: m2, estacionamientos, etc.).
COLUMNAS_CON_INDICADOR = [
    "m2_util",
    "m2_total",
    "gastos_comunes",
    "estacionamientos",
    "antiguedad_anios",
    "bodega",
]

# Encodings de categorías.
CATEGORICAS_ONEHOT = ["tipo_propiedad", "fuente"]

# Umbral de avisos por comuna para agrupar las raras en `comuna_otra`.
#
# Criterio: con n < 20 el target-mean encoding de esa comuna es ruido (la
# estimación de ~5% de la muestra mínima de 400 que se suele pedir para un
# efecto estable). Por debajo de este umbral la comuna se funde con "otras".
UMBRAL_COMUNA_MIN_AVISOS = 20
CATEGORIA_COMUNA_OTRA = "comuna_otra"

# Target-mean encoding con smoothing: el encoding es un promedio ponderado
# entre la media de la comuna y la media global, con peso proporcional al nº
# de avisos. `SMOOTHING` (m) define cuántos avisos se necesitan para que la
# comuna "pese" tanto como el prior global. Valor típico: 10-30.
SMOOTHING_TARGET_ENCODING = 20

# Outliers de precio: se detectan con el método IQR sobre el log del precio
# (el rango intercuartílico del log es estable, no lo inflan los valores
# extremos). `MULTIPLICADOR_IQR` es el factor de campana: valores fuera de
# [Q1 - k*IQR, Q3 + k*IQR] del log se descartan.
MULTIPLICADOR_IQR = 3.0
