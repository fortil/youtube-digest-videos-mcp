#!/usr/bin/env python3
"""Servidor MCP `youtube-digest` (stdio).

Herramientas: digest (digerir un video de YouTube a texto completo, con
caché persistente), get_video, list_videos, search_videos.
El texto queda guardado en SQLite indexado por video_id: llamadas repetidas
con la misma URL devuelven lo ya almacenado sin gastar otra llamada a Gemini.
"""

from __future__ import annotations

from yt_digester import config, gemini, metadata
from yt_digester.store import Store, VideoRecord
from yt_digester.urls import canonical_url, video_id_from_url
from mcp.server.mcpserver import MCPServer

m = MCPServer("youtube-digest")
_store = Store(config.DB_PATH, config.MD_DIR)


def _resolve(url: str) -> str:
    video_id = video_id_from_url(url)
    if not video_id:
        raise ValueError(
            f"'{url}' no parece un video de YouTube. Acepta watch?v=, youtu.be/, "
            f"shorts/, embed/ o el id de 11 caracteres."
        )
    return video_id


def _record_to_dict(rec: VideoRecord, cached: bool) -> dict:
    return {
        "video_id": rec.video_id,
        "url": rec.url,
        "title": rec.title,
        "channel": rec.channel,
        "language": rec.language,
        "duration_s": rec.duration_s,
        "published_at": rec.published_at,
        "summary": rec.summary,
        "key_points": rec.key_points,
        "topics": rec.topics,
        "full_text": rec.full_text,
        "model": rec.model,
        "digested_at": rec.digested_at,
        "fetch_count": rec.fetch_count,
        "cached": cached,
    }


@m.tool()
def digest(url: str, force: bool = False, language: str | None = None) -> dict:
    """Digege un video de YouTube: obtiene el texto completo del video (vía
    Gemini, que ve audio e imagen por URL) y lo guarda indexado para siempre.

    Si el video ya fue digerido, devuelve la versión guardada sin gastar otra
    llamada. Usa force=True para re-digerir, y language (ej. 'es', 'en') para
    pedir el texto completo en un idioma concreto (por defecto, el original
    del video). El resumen corto siempre viene en español.
    """
    try:
        video_id = _resolve(url)
    except ValueError as e:
        return {"error": str(e)}

    canonical = canonical_url(video_id)

    existing = _store.get(video_id)
    if existing and not force:
        _store.touch(video_id)
        existing.fetch_count += 1
        return _record_to_dict(existing, cached=True)

    fatal = metadata.precheck(canonical)
    if fatal:
        return {"error": fatal}

    try:
        result = gemini.digest_video(canonical, language=language)
    except RuntimeError as e:
        return {"error": str(e)}

    # oEmbed enriquece título/canal si Gemini no los trajo (best-effort).
    oembed, _status = metadata.fetch_oembed(canonical)
    rec = VideoRecord(
        video_id=video_id,
        url=canonical,
        full_text=result["full_text"],
        title=result.get("title") or (oembed or {}).get("title"),
        channel=result.get("channel") or (oembed or {}).get("author_name"),
        language=result.get("language"),
        duration_s=result.get("duration_s"),
        model=result.get("model"),
        summary=result.get("summary"),
        key_points=result.get("key_points", []),
        topics=result.get("topics", []),
    )
    _store.upsert(rec)
    return _record_to_dict(rec, cached=False)


@m.tool()
def get_video(url: str) -> dict:
    """Devuelve el digest guardado de un video SIN llamar a Gemini (error si
    aún no ha sido digerido — usa digest para digerirlo primero)."""
    try:
        video_id = _resolve(url)
    except ValueError as e:
        return {"error": str(e)}
    rec = _store.get(video_id)
    if not rec:
        return {"error": f"el video {video_id} no está digerido todavía"}
    return _record_to_dict(rec, cached=True)


@m.tool()
def list_videos() -> dict:
    """Lista los videos ya digeridos (metadatos, sin el texto completo)."""
    videos = _store.list_videos()
    return {"count": len(videos), "videos": videos}


@m.tool()
def search_videos(query: str) -> dict:
    """Busca en el texto completo, título y resumen de los videos digeridos
    (búsqueda de texto completo; devuelve fragmentos con la coincidencia)."""
    try:
        results = _store.search(query)
    except Exception as e:  # noqa: BLE001 — sintaxis FTS inválida, etc.
        return {"error": f"consulta inválida: {e}"}
    return {"count": len(results), "results": results}


if __name__ == "__main__":
    m.run(transport="stdio")
