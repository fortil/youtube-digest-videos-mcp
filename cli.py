#!/usr/bin/env python3
"""CLI de smoke test del digester, fuera del MCP.

Uso:
    python cli.py <url> [--force] [--language es]
    python cli.py --list
    python cli.py --get <url>
    python cli.py --search "consulta"

Imprime JSON en stdout; errores en stderr con exit code 1.
"""

from __future__ import annotations

import argparse
import json
import sys

from yt_digester import config
from yt_digester.store import Store
from yt_digester.urls import canonical_url, video_id_from_url


def _load_store() -> Store:
    return Store(config.DB_PATH, config.MD_DIR)


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke test del youtube-digester")
    ap.add_argument("url", nargs="?", help="URL (o id) del video a digerir")
    ap.add_argument("--force", action="store_true", help="re-digerir aunque esté en caché")
    ap.add_argument("--language", default=None, help="idioma del texto completo (ej. es)")
    ap.add_argument("--list", action="store_true", help="listar videos digeridos")
    ap.add_argument("--get", metavar="URL", help="devolver digest guardado sin llamar a Gemini")
    ap.add_argument("--search", metavar="QUERY", help="búsqueda de texto completo")
    args = ap.parse_args()

    store = _load_store()
    try:
        if args.list:
            videos = store.list_videos()
            print(json.dumps({"count": len(videos), "videos": videos},
                             ensure_ascii=False, indent=2))
            return
        if args.search:
            results = store.search(args.search)
            print(json.dumps({"count": len(results), "results": results},
                             ensure_ascii=False, indent=2))
            return
        if args.get:
            video_id = video_id_from_url(args.get)
            if not video_id:
                _fail(f"'{args.get}' no parece un video de YouTube")
            rec = store.get(video_id)
            if not rec:
                _fail(f"el video {video_id} no está digerido todavía")
            print(json.dumps(rec.__dict__, ensure_ascii=False, indent=2))
            return
        if not args.url:
            ap.print_help()
            sys.exit(2)

        from yt_digester import gemini, metadata

        video_id = video_id_from_url(args.url)
        if not video_id:
            _fail(f"'{args.url}' no parece un video de YouTube")
        canonical = canonical_url(video_id)

        existing = store.get(video_id)
        if existing and not args.force:
            store.touch(video_id)
            existing.fetch_count += 1
            print(json.dumps({"cached": True, **existing.__dict__},
                             ensure_ascii=False, indent=2))
            return

        fatal = metadata.precheck(canonical)
        if fatal:
            _fail(fatal)

        result = gemini.digest_video(canonical, language=args.language)
        oembed, _status = metadata.fetch_oembed(canonical)
        from yt_digester.store import VideoRecord
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
        store.upsert(rec)
        print(json.dumps({"cached": False, **rec.__dict__}, ensure_ascii=False, indent=2))
    finally:
        store.close()


def _fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
