"""Persistencia del modelo de valoración y su setup.

El artefacto guardado es un dict con el modelo ajustado, el setup del feature
engineering (medianas, encodings, umbrales), las columnas de la matriz y los
resultados de la validación, para que la API pueda cargar el modelo y hacer
score sin reentrenar. Se serializa con `joblib` (robusto para estimadores de
sklearn y DataFrames del setup).
"""

from __future__ import annotations

from pathlib import Path

import joblib

from src.paths import RAIZ_PROYECTO


# Un artefacto por tipo de operación: venta y arriendo son modelos distintos y
# no deben sobrescribirse (la API elige el modelo según la operación pedida).
def ruta_modelo(tipo_operacion: str) -> Path:
    """Ruta canónica del artefacto para una operación (anclada a la raíz)."""
    return RAIZ_PROYECTO / "models" / f"modelo_{tipo_operacion}.joblib"


def guardar_modelo(artefacto: dict, ruta: str | Path) -> Path:
    """Guarda el artefacto (dict) como joblib y devuelve la ruta usada."""
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artefacto, destino)
    return destino


def cargar_modelo(ruta: str | Path) -> dict:
    """Carga un artefacto guardado con `guardar_modelo`."""
    return joblib.load(ruta)
