"""Tests de src/scraping/pi_nordic.py contra HTML real (ver fixtures/)."""

from src.scraping.pi_nordic import extraer_estado_inicial, extraer_nordic


def test_extraer_nordic(html_pi_listado):
    nordic = extraer_nordic(html_pi_listado)
    assert nordic.get("framework") == "nordic"
    assert nordic["appProps"]["pageProps"]["initialState"]["pagination"]


def test_extraer_estado_inicial(html_pi_listado):
    estado = extraer_estado_inicial(html_pi_listado)
    assert isinstance(estado["results"], list)


def test_extraer_nordic_sin_script():
    """Un HTML sin el script (ej. página de bloqueo) devuelve dicts vacíos."""
    assert extraer_nordic("<html><body>Bloqueado</body></html>") == {}
    assert extraer_estado_inicial("<html><body>Bloqueado</body></html>") == {}


def test_extraer_nordic_ignora_statements_posteriores():
    """El script mezcla JSON con JS: raw_decode debe tomar solo el objeto."""
    html = (
        '<html><script id="__NORDIC_RENDERING_CTX__">'
        '_n.ctx.r={"framework":"nordic"};'
        "_n.ctx.r.assets.manifest=new Map([['a.css','a']]);"
        "</script></html>"
    )
    assert extraer_nordic(html) == {"framework": "nordic"}
