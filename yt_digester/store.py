"""Almacenaje persistente: SQLite (WAL) indexado por video_id + FTS5 de texto completo.

Cada digest se espeja además como Markdown en data/digests/<video_id>.md para
lectura humana sin abrir SQLite. La DB es la fuente de la verdad.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  video_id        TEXT PRIMARY KEY,
  url             TEXT NOT NULL,
  title           TEXT,
  channel         TEXT,
  language        TEXT,
  duration_s      INTEGER,
  published_at    TEXT,
  model           TEXT,
  digested_at     TEXT NOT NULL,
  summary         TEXT,
  key_points      TEXT,   -- array JSON
  topics          TEXT,   -- array JSON
  full_text       TEXT NOT NULL,
  fetch_count     INTEGER NOT NULL DEFAULT 1,
  last_accessed_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
  title, summary, full_text,
  content='videos', content_rowid='rowid',
  tokenize='porter unicode61'  -- stemming: 'elephant' matchea 'elephants'
);

CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
  INSERT INTO videos_fts(rowid, title, summary, full_text)
  VALUES (new.rowid, new.title, new.summary, new.full_text);
END;

CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
  INSERT INTO videos_fts(videos_fts, rowid, title, summary, full_text)
  VALUES ('delete', old.rowid, old.title, old.summary, old.full_text);
END;

CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
  INSERT INTO videos_fts(videos_fts, rowid, title, summary, full_text)
  VALUES ('delete', old.rowid, old.title, old.summary, old.full_text);
  INSERT INTO videos_fts(rowid, title, summary, full_text)
  VALUES (new.rowid, new.title, new.summary, new.full_text);
END;
"""

_COLS = ("video_id, url, title, channel, language, duration_s, published_at, "
         "model, digested_at, summary, key_points, topics, full_text, "
         "fetch_count, last_accessed_at")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class VideoRecord:
    video_id: str
    url: str
    full_text: str
    title: str | None = None
    channel: str | None = None
    language: str | None = None
    duration_s: int | None = None
    published_at: str | None = None
    model: str | None = None
    digested_at: str = field(default_factory=_now_iso)
    summary: str | None = None
    key_points: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    fetch_count: int = 1
    last_accessed_at: str | None = None


class Store:
    def __init__(self, db_path: Path, md_dir: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.md_dir = md_dir
        # El SDK de MCP corre las tools síncronas en hilos de trabajo: la
        # conexión debe ser multi-hilo y el acceso serializarse con lock.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- escritura -------------------------------------------------------

    def upsert(self, rec: VideoRecord) -> None:
        """Inserta o reemplaza (force refresh) un digest y regenera el espejo .md."""
        row = {
            "video_id": rec.video_id,
            "url": rec.url,
            "title": rec.title,
            "channel": rec.channel,
            "language": rec.language,
            "duration_s": rec.duration_s,
            "published_at": rec.published_at,
            "model": rec.model,
            "digested_at": rec.digested_at,
            "summary": rec.summary,
            "key_points": json.dumps(rec.key_points, ensure_ascii=False),
            "topics": json.dumps(rec.topics, ensure_ascii=False),
            "full_text": rec.full_text,
            "last_accessed_at": _now_iso(),
        }
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ?", (rec.video_id,)
            ).fetchone()
            if exists:
                sets = ", ".join(f"{k} = :{k}" for k in row)
                self._conn.execute(
                    f"UPDATE videos SET {sets} WHERE video_id = :video_id", row
                )
            else:
                cols = ", ".join(row)
                marks = ", ".join(f":{k}" for k in row)
                self._conn.execute(
                    f"INSERT INTO videos ({cols}) VALUES ({marks})", row
                )
            self._conn.commit()
        self._write_md_mirror(rec)

    def touch(self, video_id: str) -> None:
        """Cache hit: fetch_count+1 y last_accessed_at actualizados."""
        with self._lock:
            self._conn.execute(
                "UPDATE videos SET fetch_count = fetch_count + 1, "
                "last_accessed_at = ? WHERE video_id = ?",
                (_now_iso(), video_id),
            )
            self._conn.commit()

    # --- lectura ---------------------------------------------------------

    def get(self, video_id: str) -> VideoRecord | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_COLS} FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
        return self._to_record(row) if row else None

    def list_videos(self) -> list[dict]:
        """Metadatos de todos los videos digeridos (sin full_text, para no llenar contexto)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT video_id, url, title, channel, language, duration_s, "
                "published_at, model, digested_at, summary, key_points, topics, "
                "fetch_count, last_accessed_at, length(full_text) AS text_chars "
                "FROM videos ORDER BY digested_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["key_points"] = json.loads(d["key_points"] or "[]")
            d["topics"] = json.loads(d["topics"] or "[]")
            out.append(d)
        return out

    def search(self, query: str) -> list[dict]:
        """Búsqueda de texto completo (FTS5) sobre título, resumen y texto completo."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT v.video_id, v.url, v.title, v.channel, v.language, "
                "v.digested_at, v.summary, v.fetch_count, "
                "snippet(videos_fts, 2, '»', '«', '…', 24) AS snippet "
                "FROM videos_fts JOIN videos v ON v.rowid = videos_fts.rowid "
                "WHERE videos_fts MATCH ? ORDER BY rank LIMIT 20",
                (query,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _to_record(row: sqlite3.Row) -> VideoRecord:
        return VideoRecord(
            video_id=row["video_id"],
            url=row["url"],
            title=row["title"],
            channel=row["channel"],
            language=row["language"],
            duration_s=row["duration_s"],
            published_at=row["published_at"],
            model=row["model"],
            digested_at=row["digested_at"],
            summary=row["summary"],
            key_points=json.loads(row["key_points"] or "[]"),
            topics=json.loads(row["topics"] or "[]"),
            full_text=row["full_text"],
            fetch_count=row["fetch_count"],
            last_accessed_at=row["last_accessed_at"],
        )

    def _write_md_mirror(self, rec: VideoRecord) -> None:
        """Espejo legible: data/digests/<video_id>.md (se regenera en cada upsert)."""
        fm = [
            "---",
            f"video_id: {rec.video_id}",
            f"url: {rec.url}",
            f'title: {_yaml_str(rec.title)}',
            f'channel: {_yaml_str(rec.channel)}',
            f"language: {rec.language or ''}",
            f"duration_s: {rec.duration_s if rec.duration_s is not None else ''}",
            f"model: {rec.model or ''}",
            f"digested_at: {rec.digested_at}",
            f"topics: {json.dumps(rec.topics, ensure_ascii=False)}",
            "---",
            "",
        ]
        body = [f"# {rec.title or rec.video_id}", ""]
        if rec.summary:
            body += ["## Resumen", "", rec.summary, ""]
        if rec.key_points:
            body += ["## Puntos clave", ""]
            body += [f"- {p}" for p in rec.key_points] + [""]
        body += ["## Texto completo", "", rec.full_text, ""]
        path = self.md_dir / f"{rec.video_id}.md"
        path.write_text("\n".join(fm + body), encoding="utf-8")


def _yaml_str(value: str | None) -> str:
    """Valor seguro para frontmatter YAML: quoting si tiene caracteres problemáticos."""
    s = value or ""
    if any(c in s for c in ":#'\"[]{}&*!|>%@`,") or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s
