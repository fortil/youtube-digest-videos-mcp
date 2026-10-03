# youtube-digest

[![M8ven Score](https://m8ven.ai/badge/mcp/fortil-youtube-digest-videos-mcp-1wvgvs?v=fbc8d7b8e1b58ec13b4d2c2dc2d24263)](https://m8ven.ai/mcp/fortil-youtube-digest-videos-mcp-1wvgvs?s=readme)

MCP server that turns YouTube videos into text. You give it a URL, Gemini
watches the video (audio and visuals) through its documented YouTube-URL
input, and you get the full content as text plus a short summary. Results are
stored in SQLite, indexed by video id, so digesting the same URL twice returns
the stored version and costs nothing extra.

There is no downloading and no caption scraping involved. Passing a public
YouTube URL as multimodal input is a documented feature of the Gemini API
([video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)).

Any client that speaks MCP over stdio can run it: Claude Code, Claude
Desktop, Cursor, Windsurf, Cline, Continue, VS Code, ZCode.

## Tools

| Tool | What it does |
|---|---|
| `digest(url, force=False, language=None)` | Digerir un video. Cache hit returns the stored digest. `force=True` re-digests, `language` asks for the text in a given language (default: the video's own). |
| `get_video(url)` | Returns the stored digest without calling Gemini. |
| `list_videos()` | Lists digested videos with metadata. |
| `search_videos(query)` | Full-text search (SQLite FTS5, porter stemming) over titles, summaries and full texts. |

The full text stays in the video's original language; the short summary comes
in Spanish. In practice you say "digiere this video" to your assistant and it
calls `digest`, then processes or presents the text however you asked.

## Setup

```bash
git clone <repo> && cd youtube-digest-videos-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your GEMINI_API_KEY in it
```

Get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
The key lives only in `.env`, which is gitignored. Never commit it.

Smoke test without an MCP client:

```bash
.venv/bin/python cli.py "https://www.youtube.com/watch?v=jNQXAC9IVRw"
.venv/bin/python cli.py --list
.venv/bin/python cli.py --search "some words"
```

### Registering in ZCode

Add to the `mcp.servers` object in `~/.zcode/cli/config.json`:

```json
"youtube-digest": {
  "command": "/absolute/path/to/youtube-digest-videos-mcp/.venv/bin/python",
  "args": ["/absolute/path/to/youtube-digest-videos-mcp/server.py"]
}
```

## Where the data lives

- `data/digests.db` - SQLite database (WAL mode). One row per video: text,
  summary, key points, topics, language, model used, fetch counter.
- `data/digests/<video_id>.md` - a readable Markdown mirror of each digest.

Both are gitignored. The digests reproduce third-party video content, so they
belong on your machine only; see `docs/reporte_2026-09-29_riesgos-publicacion-github.md`
before publishing anything from this repo.

## Models

The server tries a chain of models and uses the first one that responds:
`gemini-3.5-flash`, then `gemini-3-flash-preview`, then
`gemini-flash-lite-latest`. The chain skips models that are gone (404) or
saturated (503) and retries once after 20 seconds when everything is busy.
As of September 2026 the `gemini-2.5-*` family returns 404 for new keys.

Override with `GEMINI_MODEL` (single model) or `GEMINI_MODELS`
(comma-separated chain) in `.env`. The model that produced each digest is
recorded in its row.

## Limits and costs

- Only public videos. Private, unlisted-restricted or deleted videos are
  rejected via a free oEmbed check before any Gemini call is spent.
- Gemini bills per video second (roughly 300 tokens per second of media).
  Long videos cost more; a 90-minute video can also hit output limits and
  produce a truncated text.
- Free-tier keys have per-day video limits; paid keys are billed per token.
- An exposed key is a billable key. Turn on budget alerts in AI Studio and
  keep `.env` out of git (GitHub's push protection is a safety net, not a plan).

## License

MIT. Personal project, not affiliated with Google or YouTube. You use your
own API key under your own terms of service.
