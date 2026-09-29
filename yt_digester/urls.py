"""Normalización de referencias a YouTube → video_id de 11 chars.

Portado de knowledge-generator/scripts/common.py:517 (video_id_from_url).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id_from_url(url_or_id: str) -> str | None:
    """Normaliza CUALQUIER forma de referencia a YouTube a su video_id de 11 chars.

    Acepta: 'fVWuTEjv3nc', 'https://youtu.be/fVWuTEjv3nc?t=10',
    'https://www.youtube.com/watch?v=fVWuTEjv3nc&list=...', '/shorts/<id>', '/embed/<id>'.
    Devuelve None si no parece un video de YouTube.
    """
    s = (url_or_id or "").strip()
    if _YT_ID_RE.match(s):
        return s
    try:
        u = urlparse(s)
    except ValueError:
        return None
    host = (u.netloc or "").lower().lstrip("www.")
    if host == "youtu.be":
        # tolera URLs pegadas con '&' en vez de '?': 'youtu.be/<id>&t=5'
        cand = u.path.lstrip("/").split("/")[0].split("&")[0].split("?")[0]
        return cand if _YT_ID_RE.match(cand) else None
    if "youtube.com" in host or host.endswith("youtube.com"):
        qs = parse_qs(u.query)
        if "v" in qs and _YT_ID_RE.match(qs["v"][0]):
            return qs["v"][0]
        # /shorts/<id>, /embed/<id>, /v/<id>
        parts = [p for p in u.path.split("/") if p]
        for i, p in enumerate(parts):
            if p in ("shorts", "embed", "v") and i + 1 < len(parts):
                cand = parts[i + 1]
                return cand if _YT_ID_RE.match(cand) else None
    return None


def canonical_url(video_id: str) -> str:
    """URL canónica que se pasa a Gemini (FileData) y se guarda en la DB."""
    return f"https://www.youtube.com/watch?v={video_id}"
