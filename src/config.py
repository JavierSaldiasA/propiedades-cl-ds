"""Configuración central del proyecto.

Lee variables desde `.env` (ver `.env.example`). Nunca hardcodear credenciales.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.paths import RAIZ_PROYECTO


class Configuraciones(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url_database: str
    usuario_bcch: str
    password_bcch: str


@lru_cache
def obtener_configuraciones() -> Configuraciones:
    """Devuelve la configuración (se instancia solo cuando se necesita,
    para que los tests no requieran un `.env` presente)."""
    return Configuraciones()
