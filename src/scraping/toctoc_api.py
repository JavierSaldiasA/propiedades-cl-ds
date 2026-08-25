"""Cliente del API de búsqueda de TOCTOC.

TOCTOC es una SPA React: las páginas de resultados no traen datos y el
buscador vive en un API interna (POST /api/mapa/GetProps) protegida con
un JWT de sesión que el sitio genera en cualquier página (script
react-engine-props, válido ~7 días). Este módulo obtiene el token y
ejecuta búsquedas paginadas.

La ficha de cada propiedad, en cambio, es server-rendered (Next.js): se
descarga con GET directo y se parsea su __NEXT_DATA__ (toctoc_ficha.py).

Verificado contra el API real el 2026-08-24.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

URL_RESULTADOS = "https://www.toctoc.com/resultados/lista/compra"
URL_GET_PROPS = "https://www.toctoc.com/api/mapa/GetProps"

# Código de operacion del API: 1 = venta, 2 = arriendo
OPERACIONES = {"venta": 1, "arriendo": 2}

# Filtro de estado: 0 = todas, 1 = proyectos, 2 = usadas. Se scrapearon solo
# las usadas (avisos individuales): los proyectos tienen precio "desde" y
# specs en rangos (misma decisión que Portal Inmobiliario).
ESTADO_USADAS = 2

MAX_REINTENTOS = 3
ESPERA_BACKOFF_BASE = 5.0  # segundos

# Cuerpo del POST observado en el navegador; los campos de tipo de propiedad
# y superficie no filtran (el API los ignora): el filtro por tipo se hace por
# el patrón de la URL de cada propiedad (ver toctoc_listado.py).
CUERPO_BUSQUEDA = {
    "region": "",
    "comuna": "",
    "barrio": "",
    "poi": "",
    "tipoVista": "lista",
    "idPoligono": None,
    "moneda": 2,
    "precioDesde": 0,
    "precioHasta": 0,
    "dormitoriosDesde": 0,
    "dormitoriosHasta": 0,
    "banosDesde": 0,
    "banosHasta": 0,
    "tipoPropiedad": "",
    "disponibilidadEntrega": "",
    "numeroDeDiasTocToc": 0,
    "superficieDesdeUtil": 0,
    "superficieHastaUtil": 0,
    "superficieDesdeConstruida": 0,
    "superficieHastaConstruida": 0,
    "superficieDesdeTerraza": 0,
    "superficieHastaTerraza": 0,
    "superficieDesdeTerreno": 0,
    "superficieHastaTerreno": 0,
    "ordenarPor": 0,
    "paginaInterna": 1,
    "zoom": 15,
    "idZonaHomogenea": 0,
    "busqueda": "",
    "viewport": "",
    "atributos": [],
    "publicador": 0,
    "temporalidad": 0,
    "limite": 510,
    "cargaBanner": True,
    "primeraCarga": True,
    "santander": False,
}


def obtener_token(cliente: httpx.Client) -> str:
    """JWT de sesión, extraído del script react-engine-props de una página."""
    respuesta = cliente.get(URL_RESULTADOS)
    respuesta.raise_for_status()
    inicio = respuesta.text.find('id="react-engine-props"')
    if inicio == -1:
        raise ValueError("No se encontró el script react-engine-props")
    inicio_json = respuesta.text.find(">", inicio) + 1
    fin_json = respuesta.text.find("</script>", inicio_json)
    datos = json.loads(respuesta.text[inicio_json:fin_json])
    token = datos.get("token")
    if not token:
        raise ValueError("La página no trae token de sesión")
    return token


def buscar(
    cliente: httpx.Client,
    token: str,
    operacion: str,
    pagina: int,
    estado: int = ESTADO_USADAS,
) -> dict:
    """Página `pagina` de resultados del buscador, como dict.

    Reintenta con backoff exponencial ante 429/5xx, como descargar() de
    cliente_http (que es GET-only; esta es la variante POST).
    """
    cuerpo = {**CUERPO_BUSQUEDA, "operacion": OPERACIONES[operacion], "estado": estado}
    cuerpo["pagina"] = pagina
    for intento in range(1, MAX_REINTENTOS + 1):
        respuesta = cliente.post(
            URL_GET_PROPS,
            json=cuerpo,
            headers={
                "x-access-token": token,
                "Referer": URL_RESULTADOS,
                "Accept": "application/json",
            },
        )
        if respuesta.status_code in (429, 500, 502, 503):
            espera = ESPERA_BACKOFF_BASE * (2 ** (intento - 1))
            logger.warning(
                "HTTP %d en búsqueda %s pág %d; reintento %d en %.0fs",
                respuesta.status_code,
                operacion,
                pagina,
                intento,
                espera,
            )
            time.sleep(espera)
            continue
        respuesta.raise_for_status()
        return respuesta.json()
    raise httpx.HTTPError(
        f"Sin éxito tras {MAX_REINTENTOS} reintentos en {URL_GET_PROPS}"
    )
