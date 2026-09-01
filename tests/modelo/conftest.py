"""Fixtures compartidos de los tests del módulo de modelado."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

_FACTOR_COMUNA = {"Las Condes": 220, "Santiago": 90, "Otra": 130}


def construir_df_propiedades(
    n_las_condes: int = 60, n_santiago: int = 50, n_otra: int = 40
) -> pd.DataFrame:
    """DataFrame sintético con el schema de `properties` y señal por comuna.

    El precio depende de la comuna y los m² (más algo de ruido): esto da señal
    para que los baselines rindan mejor que predecir la mediana.
    """
    rng = np.random.default_rng(20260901)
    filas: list[dict] = []

    def _agregar(comuna: str, n: int) -> None:
        for _ in range(n):
            m2_util = float(rng.normal(75, 15))
            base = _FACTOR_COMUNA[comuna]
            precio = base * max(m2_util, 10) * float(np.exp(rng.normal(0, 0.15)))
            filas.append(
                {
                    "fuente": rng.choice(("yapo", "toctoc", "portal_inmobiliario")),
                    "url_origen": f"https://ejemplo.cl/{comuna}/{rng.integers(1e9)}",
                    "tipo_operacion": "venta",
                    "tipo_propiedad": rng.choice(("casa", "departamento")),
                    "precio_valor": precio,
                    "precio_moneda": "CLP",
                    "precio_clp_normalizado": precio,
                    "m2_util": m2_util,
                    "m2_total": m2_util + float(rng.normal(20, 8)),
                    "gastos_comunes": float(rng.integers(0, 200_000)),
                    "dormitorios": int(rng.integers(2, 5)),
                    "banos": int(rng.integers(1, 4)),
                    "estacionamientos": int(rng.integers(0, 3)),
                    "bodega": None if rng.random() < 0.15 else bool(rng.integers(0, 2)),
                    "comuna": comuna,
                    "region": "13",
                    "antiguedad_anios": int(rng.integers(0, 31)),
                    "descripcion": "",
                    "fecha_publicacion": pd.Timestamp("2026-08-01"),
                    "fecha_scraping": pd.Timestamp("2026-08-30"),
                }
            )

    _agregar("Las Condes", n_las_condes)
    _agregar("Santiago", n_santiago)
    _agregar("Otra", n_otra)
    df = pd.DataFrame(filas)
    for col in ("m2_util", "m2_total", "gastos_comunes"):
        df.loc[0:2, col] = np.nan
    df["bodega"] = df["bodega"].astype("boolean")
    return df


@pytest.fixture
def df_propiedades() -> pd.DataFrame:
    return construir_df_propiedades()
