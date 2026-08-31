"""Orquestador de scraping compartido por las fuentes.

Los tres scrapers (Yapo, Portal Inmobiliario y TOCTOC) comparten el mismo
esqueleto: recorren páginas de listado, extraen tarjetas, visitan las
fichas/detalles de hasta `--max-detalles` avisos y guardan en
data/raw/<fuente>/<run_id>/ los snapshots crudos comprimidos (html/*.gz,
JSON o HTML según la fuente) más un parquet con los campos tal como se
scrapearon (sin normalizar; eso es trabajo del ETL).

Este módulo extrae esa lógica común. Cada fuente subclasifica `ScraperBase`
aportando solo lo que le es propio (cómo recorre y guarda los listados, y qué
parser de detalle usa); el resto —columnas, tipos, merge, manejo de errores,
`--reparsear` y el flujo de `main()`— es idéntico.
"""

from __future__ import annotations

import gzip
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.scraping.cliente_http import (
    ErrorBloqueo,
    crear_cliente,
    descargar,
    descargar_aviso,
    esperar,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contrato único de columnas.
# ---------------------------------------------------------------------------

# Columnas del parquet crudo de scraping, en orden. Es la fuente de verdad de
# qué guarda cada fuente; el ETL y el schema.sql de la BD se derivan de aquí.
COLUMNAS = [
    "adid",
    "url_origen",
    "categoria_slug",
    "tipo_operacion",
    "tipo_propiedad",
    "titulo",
    "precio_texto",
    "precio_valor",
    "precio_moneda",
    "comuna",
    "region",
    "m2_tarjeta",
    "dormitorios",
    "banos",
    "estacionamientos",
    "vendedor",
    "es_profesional",
    "etiqueta",
    "descuento_pct",
    "descripcion",
    "fecha_publicacion",
    "m2_construida",
    "m2_totales",
    "gastos_comunes",
    "anio_construccion",
    "piso",
    "piscina",
    "bodega",
    "beneficios",
    "latitud",
    "longitud",
    "fecha_scraping",
]

COLUMNAS_ENTERAS = (
    "dormitorios",
    "banos",
    "estacionamientos",
    "anio_construccion",
    "piso",
)
COLUMNAS_FLOTANTES = (
    "precio_valor",
    "m2_tarjeta",
    "m2_construida",
    "m2_totales",
    "gastos_comunes",
    "descuento_pct",
    "latitud",
    "longitud",
)
COLUMNAS_BOOLEANAS = ("es_profesional", "piscina", "bodega")
COLUMNAS_FECHAS = ("fecha_publicacion", "fecha_scraping")


# ---------------------------------------------------------------------------
# Herramientas de persistencia.
# ---------------------------------------------------------------------------


def guardar_gzip(ruta: Path, contenido: str) -> None:
    with gzip.open(ruta, "wt", encoding="utf-8") as archivo:
        archivo.write(contenido)


def leer_gzip(ruta: Path) -> str:
    with gzip.open(ruta, "rt", encoding="utf-8") as archivo:
        return archivo.read()


def a_dataframe(registros: dict[str, dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(registros.values())).reindex(columns=COLUMNAS)
    for columna in COLUMNAS_ENTERAS:
        df[columna] = df[columna].astype("Int64")
    for columna in COLUMNAS_FLOTANTES:
        df[columna] = df[columna].astype("Float64")
    for columna in COLUMNAS_BOOLEANAS:
        df[columna] = df[columna].astype("boolean")
    for columna in COLUMNAS_FECHAS:
        df[columna] = pd.to_datetime(df[columna])
    return df


def escribir_parquet(registros: dict[str, dict], directorio: Path) -> None:
    if not registros:
        logger.warning("No hay registros; no se escribe parquet.")
        return
    ruta = directorio / "propiedades.parquet"
    a_dataframe(registros).to_parquet(ruta, index=False)
    logger.info("Parquet escrito: %s (%d avisos)", ruta, len(registros))


def fusionar_detalle(registro: dict, detalle: dict, proteger_url: bool = False) -> None:
    """Merge de la ficha/detalle sobre el registro del listado.

    Con `proteger_url=True` (TOCTOC) no se sobrescribe `url_origen`: la ficha
    reporta una URL canónica con hash distinta de la del listado, y la dedup de
    la BD depende de una URL estable por aviso.
    """
    if proteger_url:
        registro.update(
            {k: v for k, v in detalle.items() if v is not None and k != "url_origen"}
        )
        return
    registro.update({k: v for k, v in detalle.items() if v is not None})


# ---------------------------------------------------------------------------
# Orquestador por fuente.
# ---------------------------------------------------------------------------


class ScraperBase:
    """Flujo de scraping compartido. Las fuentes heredan y completan.

    Cada subclase implementa `_scrapear_listados`, `parsear_detalle` y
    `_leer_listado`. El resto (detalles, parquet, errores, `--reparsear` y
    `main`) vive acá.
    """

    nombre: str = "base"
    directorio_raw = Path("data/raw/base")
    proteger_url_en_ficha: bool = False
    patron_listado = "listado_*.html.gz"
    # Errores que abortan la corrida conservando el parquet parcial.
    clases_aborto: tuple = (ErrorBloqueo, KeyboardInterrupt)

    # --- a implementar por cada fuente ------------------------------------

    def _scrapear_listados(self, args, cliente, directorio_html, registros) -> None:
        raise NotImplementedError

    def parsear_detalle(self, html: str) -> dict:
        raise NotImplementedError

    def _leer_listado(self, ruta: Path) -> list[dict]:
        """Re-parsea un snapshot de listado a registros (para --reparsear)."""
        raise NotImplementedError

    def _preparar(self, args, cliente):
        """Hook opcional (ej. los scrapers que necesitan un token de sesión)."""

    # --- listados paginados por URL (Yapo y Portal Inmobiliario) -----------

    def _scrapear_listados_por_url(
        self,
        args,
        cliente,
        directorio_html,
        registros,
        *,
        construir_url,
        parsear_tarjetas,
        obtener_url_siguiente,
        parsear_total,
    ) -> None:
        """Recorre `args.categorias`, pagina por URL y guarda cada HTML."""
        for categoria in args.categorias:
            url: str | None = construir_url(categoria)
            pagina = 0
            while url and pagina < args.max_paginas:
                pagina += 1
                logger.info("Listado %s página %d: %s", categoria, pagina, url)
                try:
                    html = descargar(url, cliente)
                except Exception as error:
                    if not self._log_http_listado(error, categoria):
                        raise
                    break
                guardar_gzip(
                    directorio_html / f"listado_{categoria}_p{pagina}.html.gz", html
                )
                if pagina == 1:
                    total = parsear_total(html)
                    logger.info("  Total de avisos en la categoría: %s", total)
                try:
                    tarjetas = parsear_tarjetas(html, categoria)
                except Exception:
                    logger.exception("  Error parseando %s; se omite la página", url)
                    break
                logger.info("  %d tarjetas extraídas", len(tarjetas))
                for tarjeta in tarjetas:
                    tarjeta["fecha_scraping"] = date.today()
                    registros.setdefault(tarjeta["adid"], tarjeta)
                url = obtener_url_siguiente(html)
                if url and pagina < args.max_paginas:
                    esperar(args.delay)

    @staticmethod
    def _log_http_listado(error: Exception, categoria: str) -> bool:
        """Log de un fallo HTTP de listado; False si no es un HTTPStatusError.

        Devuelve True si el error se manejó (HTTP con status) y False si debe
        propagarse (otro tipo de error).
        """
        respuesta = getattr(error, "response", None)
        if respuesta is None:
            return False
        logger.error(
            "Listado no disponible (HTTP %d); se pasa a la siguiente categoría",
            respuesta.status_code,
        )
        return True

    # --- esqueleto compartido ---------------------------------------------

    def _scrapear_detalles(self, args, cliente, directorio_html, registros) -> None:
        candidatos = list(registros.values())[: args.max_detalles]
        for indice, registro in enumerate(candidatos, start=1):
            logger.info(
                "Detalle %d/%d: %s", indice, len(candidatos), registro["url_origen"]
            )
            html = descargar_aviso(registro["url_origen"], cliente)
            if html is None:  # aviso dado de baja entre listado y detalle
                continue
            guardar_gzip(directorio_html / f"detalle_{registro['adid']}.html.gz", html)
            try:
                detalle = self.parsear_detalle(html)
            except Exception:
                logger.exception(
                    "  Error parseando detalle %s; se conserva la tarjeta",
                    registro["adid"],
                )
                continue
            fusionar_detalle(registro, detalle, self.proteger_url_en_ficha)
            if indice < len(candidatos):
                esperar(args.delay)

    def reparsear(self, run_id: str) -> None:
        """Regenera el parquet de una corrida desde sus snapshots, sin red.

        Re-parsea los snapshots de listado y ficha ya guardados con los parsers
        actuales (útil cuando se agrega un campo nuevo) y escribe un nuevo
        run_id con el parquet; los crudos originales quedan intactos.
        """
        directorio_origen = self.directorio_raw / run_id / "html"
        if not directorio_origen.is_dir():
            raise SystemExit(
                f"No existe el directorio de snapshots: {directorio_origen}"
            )

        try:
            fecha_corrida = datetime.strptime(run_id.split("_")[0], "%Y%m%d").date()
        except ValueError:
            fecha_corrida = date.today()

        registros: dict[str, dict] = {}
        for ruta in sorted(directorio_origen.glob(self.patron_listado)):
            avisos = self._leer_listado(ruta)
            logger.info("Listado %s: %d avisos", ruta.name, len(avisos))
            for aviso in avisos:
                aviso["fecha_scraping"] = fecha_corrida
                registros.setdefault(aviso["adid"], aviso)

        fichas = 0
        for ruta in sorted(directorio_origen.glob("detalle_*.html.gz")):
            adid = ruta.stem.removeprefix("detalle_").removesuffix(".html")
            registro = registros.get(adid)
            if registro is None:
                continue  # ficha de una página que ya no se parsea
            try:
                detalle = self.parsear_detalle(leer_gzip(ruta))
            except Exception:
                logger.exception(
                    "  Error parseando %s; se conserva el listado", ruta.name
                )
                continue
            if detalle:
                fusionar_detalle(registro, detalle, self.proteger_url_en_ficha)
                fichas += 1

        run_nuevo = datetime.now().strftime("%Y%m%d_%H%M%S")
        directorio_salida = self.directorio_raw / run_nuevo
        directorio_salida.mkdir(parents=True, exist_ok=True)
        escribir_parquet(registros, directorio_salida)
        logger.info(
            "Re-parseo de %s listo: %d avisos (%d con ficha) en %s",
            run_id,
            len(registros),
            fichas,
            directorio_salida,
        )

    def main(self, args) -> None:
        if getattr(args, "reparsear", None):
            self.reparsear(args.reparsear)
            return

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        directorio_salida = self.directorio_raw / run_id
        directorio_html = directorio_salida / "html"
        directorio_html.mkdir(parents=True, exist_ok=True)
        logger.info("Directorio de salida: %s", directorio_salida)

        registros: dict[str, dict] = {}  # adid -> registro (dedup por adid)
        cliente = crear_cliente()
        try:
            self._preparar(args, cliente)
            self._scrapear_listados(args, cliente, directorio_html, registros)
            if args.max_detalles > 0:
                self._scrapear_detalles(args, cliente, directorio_html, registros)
        except self.clases_aborto as error:
            logger.error("Corrida abortada: %s", error)
        finally:
            cliente.close()
            escribir_parquet(registros, directorio_salida)

        logger.info("Listo: %d avisos únicos en %s", len(registros), directorio_salida)
