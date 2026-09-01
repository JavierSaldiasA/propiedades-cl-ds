"""Entrenamiento del modelo baseline de valoración (CLI).

Flujo:
1. Lee las propiedades de Supabase (`src/eda.leer.cargar_properties`).
2. Ajusta el setup global del feature engineering (sin outliers).
3. Evalúa comparativamente los baselines con CV honesto (target encoding por fold).
4. Reentrena el mejor modelo sobre todos los datos y guarda el artefacto
   (modelo + setup + columnas + resultados) como joblib.

Ejemplo:
    python -m src.modelo.entrenar --tipo-operacion venta --folds 5
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.eda.leer import cargar_properties
from src.features.construir import construir_matriz
from src.modelo.persistencia import guardar_modelo, ruta_modelo
from src.modelo.validacion import (
    aplicar_clip,
    calcular_clip,
    evaluar_cv,
    modelos_baseline,
    preparar_ajuste,
    preparar_x,
)


def _metricas_finales(modelo: Any, x: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    from src.modelo.metricas import metricas_regresion

    return metricas_regresion(y, modelo.predict(x))


def entrenar(
    tipo_operacion: str,
    n_folds: int = 5,
    semilla: int = 42,
    salida: str | Path | None = None,
) -> dict:
    """Entrena, valida y guarda el modelo. Devuelve el artefacto guardado.

    Sin `salida`, el artefacto se guarda en `models/modelo_<operacion>.joblib`
    (venta y arriendo no se sobrescriben entre sí).
    """
    df = cargar_properties(tipo_operacion)
    if df.empty:
        raise SystemExit(f"No hay filas para `{tipo_operacion}` en la base de datos.")

    df_limpio, setup = preparar_ajuste(df)
    clip = calcular_clip(df_limpio, setup)
    if len(df_limpio) < 2 * n_folds:
        raise SystemExit(
            "Dataset demasiado pequeño para CV: "
            f"{len(df_limpio)} filas con {n_folds} folds."
        )

    por_fold, resumen = evaluar_cv(df_limpio, n_folds=n_folds, semilla=semilla)
    print("\n== CV honesto (KFold, target encoding por fold) ==")
    print(resumen.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))

    mejor = resumen.iloc[0]["modelo"]
    fabricas = modelos_baseline(semilla)
    modelo = fabricas[mejor]()
    x, y, _ = construir_matriz(df_limpio, setup=setup, entrenamiento=True)
    x = aplicar_clip(preparar_x(x), clip)
    modelo.fit(x, y)
    metricas = _metricas_finales(modelo, x, y)

    artefacto = {
        "modelo": modelo,
        "setup": setup,
        "clip": clip,
        "columnas": list(x.columns),
        "resultados_cv": {
            "por_fold": por_fold,
            "resumen": resumen,
        },
        "metricas_en_fit": metricas,
        "metadatos": {
            "creado": datetime.now().isoformat(timespec="seconds"),
            "tipo_operacion": tipo_operacion,
            "n_folds": n_folds,
            "semilla": semilla,
            "n_avisos": int(len(df_limpio)),
            "modelo_elegido": mejor,
            "precio_promedio_clp": float(np.expm1(df_limpio["precio_log"].mean())),
        },
    }
    if salida is None:
        salida = ruta_modelo(tipo_operacion)
    ruta = guardar_modelo(artefacto, salida)
    print(f"\nMejor modelo: {mejor}")
    print(f"Artefacto guardado en: {ruta}")
    return artefacto


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tipo-operacion",
        choices=("venta", "arriendo"),
        default="venta",
        help="Operación a modelar (default: venta).",
    )
    parser.add_argument(
        "--folds",
        type=int,
        default=5,
        help="Número de folds del CV (default: 5).",
    )
    parser.add_argument(
        "--semilla",
        type=int,
        default=42,
        help="Semilla fija del CV y los modelos (default: 42).",
    )
    parser.add_argument(
        "--salida",
        default=None,
        help=(
            "Ruta del artefacto joblib. Por defecto "
            "models/modelo_<tipo-operacion>.joblib (venta y arriendo no se "
            "sobrescriben entre sí)."
        ),
    )
    return parser


def main() -> None:
    args = _arg_parser().parse_args()
    entrenar(
        args.tipo_operacion,
        n_folds=args.folds,
        semilla=args.semilla,
        salida=args.salida,
    )


if __name__ == "__main__":
    main()
