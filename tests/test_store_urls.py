"""Tests de urls.py y store.py contra una DB temporal (estilo knowledge-generator/test_flow.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from yt_digester.store import Store, VideoRecord
from yt_digester.urls import canonical_url, video_id_from_url


class TestUrls(unittest.TestCase):
    def test_bare_id(self):
        self.assertEqual(video_id_from_url("fVWuTEjv3nc"), "fVWuTEjv3nc")

    def test_watch_url_with_list_param(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc&t=30"
        self.assertEqual(video_id_from_url(url), "dQw4w9WgXcQ")

    def test_youtu_be_with_timestamp(self):
        self.assertEqual(
            video_id_from_url("https://youtu.be/fVWuTEjv3nc?t=10"), "fVWuTEjv3nc"
        )
        # variante malformada pegada con '&'
        self.assertEqual(
            video_id_from_url("https://youtu.be/fVWuTEjv3nc&t=10"), "fVWuTEjv3nc"
        )

    def test_shorts_and_embed(self):
        self.assertEqual(
            video_id_from_url("https://www.youtube.com/shorts/abcdefghijk"),
            "abcdefghijk",
        )
        self.assertEqual(
            video_id_from_url("https://www.youtube.com/embed/abcdefghijk"),
            "abcdefghijk",
        )

    def test_mobile_and_m_domains(self):
        self.assertEqual(
            video_id_from_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            video_id_from_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_invalid(self):
        for bad in ("", "no es url", "https://vimeo.com/123456",
                    "https://youtube.com/watch", "https://youtu.be/short"):
            self.assertIsNone(video_id_from_url(bad), bad)

    def test_canonical(self):
        self.assertEqual(
            canonical_url("dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )


class TestStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.store = Store(base / "digests.db", base / "digests")
        self.rec = VideoRecord(
            video_id="dQw4w9WgXcQ",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            full_text="Never gonna give you up. Never gonna let you down.",
            title="Video de prueba",
            channel="Canal Test",
            language="en",
            model="gemini-2.5-flash",
            summary="Un video de prueba.",
            key_points=["punto uno", "punto dos"],
            topics=["test", "prueba"],
        )

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_roundtrip(self):
        self.store.upsert(self.rec)
        got = self.store.get("dQw4w9WgXcQ")
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "Video de prueba")
        self.assertEqual(got.key_points, ["punto uno", "punto dos"])
        self.assertIn("give you up", got.full_text)

    def test_touch_increments(self):
        self.store.upsert(self.rec)
        self.store.touch("dQw4w9WgXcQ")
        self.store.touch("dQw4w9WgXcQ")
        self.assertEqual(self.store.get("dQw4w9WgXcQ").fetch_count, 3)
        self.assertTrue(self.store.get("dQw4w9WgXcQ").last_accessed_at)

    def test_search_fts(self):
        self.store.upsert(self.rec)
        hits = self.store.search("let you DOWN")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(self.store.search("palabraquenoparece"), [])

    def test_search_stemming(self):
        """Porter: el plural indexado debe matchear el singular consultado."""
        self.store.upsert(self.rec)
        self.assertEqual(len(self.store.search("down" )), 1)
        self.assertEqual(len(self.store.search("give")), 1)  # 'give' vs 'give'+'given'

    def test_fts_stays_synced_on_update(self):
        """Force refresh: el UPDATE debe dejar el FTS consistente con el texto nuevo."""
        self.store.upsert(self.rec)
        self.rec.full_text = "Contenido totalmente renovado sobre quilombos."
        self.store.upsert(self.rec)
        self.assertEqual(self.store.search("give you up"), [])
        self.assertEqual(len(self.store.search("quilombos")), 1)

    def test_md_mirror(self):
        self.store.upsert(self.rec)
        md = self.store.md_dir / "dQw4w9WgXcQ.md"
        self.assertTrue(md.exists())
        content = md.read_text(encoding="utf-8")
        self.assertIn("title:", content)
        self.assertIn("Video de prueba", content)
        self.assertIn("## Texto completo", content)
        self.assertIn("give you up", content)

    def test_list_videos(self):
        self.store.upsert(self.rec)
        listing = self.store.list_videos()
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(listing[0]["text_chars"], len(self.rec.full_text))
        self.assertNotIn("full_text", listing[0])


if __name__ == "__main__":
    unittest.main()
