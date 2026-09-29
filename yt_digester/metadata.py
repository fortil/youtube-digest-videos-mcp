"""Metadatos de un video vía oEmbed público de YouTube (sin API key).

Doble uso: enriquece el registro (título/canal) y sirve de pre-chequeo
gratuito — un 401/403/404 de oEmbed indica video privado, restringido o
inexistente ANTES de gastar la llamada a Gemini.
"""

from __future__ import annotations

import requests

_OEMBED_URL = "https://www.youtube.com/oembed"

# Códigos que descartan el video sin gastar cuota de Gemini.
_FATAL_STATUS = (401, 403, 404)


def fetch_oembed(url: str, timeout: float = 10.0) -> tuple[dict | None, int | None]:
    """Devuelve (datos|None, status_http). datos: title, author_name, thumbnail_url..."""
    try:
        r = requests.get(
            _OEMBED_URL, params={"url": url, "format": "json"}, timeout=timeout
        )
    except requests.RequestException:
        return None, None  # sin red / timeout: no bloqueamos el flujo
    if r.status_code != 200:
        return None, r.status_code
    try:
        return r.json(), 200
    except ValueError:
        return None, 200


def precheck(url: str) -> str | None:
    """None si el video parece digerible; mensaje de error si claramente no lo es."""
    _data, status = fetch_oembed(url)
    if status in _FATAL_STATUS:
        return (
            f"oEmbed devolvió HTTP {status}: el video es privado, restringido o "
            f"inexistente. La vía Gemini-por-URL solo soporta videos públicos."
        )
    return None
