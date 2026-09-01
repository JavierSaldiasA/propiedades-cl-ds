"""Rutas del proyecto ancladas a la raíz del repositorio.

Los comandos (scraping, ETL, notebooks) pueden invocarse desde cualquier
directorio; la raíz se deduce del archivo `src/paths.py` y no del CWD. En
deploys (Docker u otros) se puede sobreescribir con la variable de entorno
`PROPIEDADES_ROOT`.
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolver_raiz() -> Path:
    override = os.environ.get("PROPIEDADES_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


RAIZ_PROYECTO = _resolver_raiz()
