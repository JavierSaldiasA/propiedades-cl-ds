"""Métricas de regresión para la valoración de propiedades.

El target del modelo es `log1p(precio)`; las métricas se reportan tanto en el
espacio del log (donde se entrena el modelo) como en CLP (donde se interpreta
el error de una valoración). Todas son funciones puras: reciben arrays de
valores reales y predichos en el espacio logarítmico.

Para pasar a CLP se usa `np.expm1` (inversa exacta se `log1p`).
"""

from __future__ import annotations

from typing import Any

import numpy as np


def metricas_regresion(y_log: Any, y_pred_log: Any) -> dict[str, float]:
    """Métricas de regresión sobre predicciones en espacio logarítmico.

    Recibe los target/valores en `log1p` (CLP) y devuelve:
    - `mae_log`, `rmse_log`, `r2_log`: sobre el log (escala del entrenamiento);
    - `mae_clp`, `rmse_clp`, `mape`: errores deshaciendo el log (`expm1`), con
      el MAPE en porcentaje sobre los precios en CLP.
    """
    y = np.asarray(y_log, dtype=float)
    y_hat = np.asarray(y_pred_log, dtype=float)
    if y.shape != y_hat.shape or y.size == 0:
        raise ValueError("`y_log` y `y_pred_log` deben tener la misma longitud > 0.")

    error = y_hat - y
    mae_log = float(np.mean(np.abs(error)))
    rmse_log = float(np.sqrt(np.mean(error**2)))

    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2_log = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    precio = np.expm1(y)
    prediccion = np.expm1(y_hat)
    mae_clp = float(np.mean(np.abs(prediccion - precio)))
    rmse_clp = float(np.sqrt(np.mean((prediccion - precio) ** 2)))
    mape = float(np.mean(np.abs(prediccion - precio) / precio) * 100)

    return {
        "mae_log": mae_log,
        "rmse_log": rmse_log,
        "r2_log": r2_log,
        "mae_clp": mae_clp,
        "rmse_clp": rmse_clp,
        "mape": mape,
    }
