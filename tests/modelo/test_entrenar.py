"""Tests del CLI de entrenamiento (sin base de datos).

Se simula `cargar_properties` y se escribe el artefacto en un directorio
temporal para cubrir el flujo completo de entrenar → elegir mejor modelo →
guardar artefacto.
"""

from __future__ import annotations

from src.modelo import entrenar
from src.modelo.persistencia import ruta_modelo


def test_arg_parser_defaults():
    args = entrenar._arg_parser().parse_args([])
    assert args.tipo_operacion == "venta"
    assert args.folds == 5
    assert args.semilla == 42
    assert args.salida is None


def test_entrenar_sin_salida_usa_ruta_por_operacion(
    tmp_path, monkeypatch, df_propiedades
):
    def _cargar_properties(tipo_operacion):
        return df_propiedades

    monkeypatch.setattr(entrenar, "cargar_properties", _cargar_properties)
    # Apuntamos la raíz del repo a tmp para no tocar models/ real en el test.
    monkeypatch.setattr("src.modelo.persistencia.RAIZ_PROYECTO", tmp_path)
    ruta = ruta_modelo("arriendo")
    assert ruta == tmp_path / "models" / "modelo_arriendo.joblib"

    entrenar.entrenar("arriendo", n_folds=2, semilla=42)
    assert ruta.exists()


def test_entrenar_guarda_artefacto(tmp_path, monkeypatch, df_propiedades):

    def _cargar_properties(tipo_operacion):
        assert tipo_operacion == "arriendo"
        return df_propiedades

    monkeypatch.setattr(entrenar, "cargar_properties", _cargar_properties)
    salida = tmp_path / "modelo.joblib"

    artefacto = entrenar.entrenar("arriendo", n_folds=2, semilla=42, salida=salida)

    assert salida.exists()
    assert set(artefacto) == {
        "modelo",
        "setup",
        "clip",
        "columnas",
        "resultados_cv",
        "metricas_en_fit",
        "metadatos",
    }
    assert artefacto["metadatos"]["tipo_operacion"] == "arriendo"
    assert artefacto["metadatos"]["modelo_elegido"] in {
        "mediana",
        "ridge",
        "random_forest",
        "hist_gradient_boosting",
    }
    assert {"mape", "mae_clp", "rmse_clp"} <= set(artefacto["metricas_en_fit"])
    # El setup se persiste con el modelo (fit/transform en score).
    assert "target_media" in artefacto["setup"]
    # Ninguna feature tautológica queda en las columnas del artefacto.
    assert "precio_por_m2_util" not in artefacto["columnas"]
