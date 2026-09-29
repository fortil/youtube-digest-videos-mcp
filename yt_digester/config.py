"""Configuración central: rutas del proyecto y variables de entorno (.env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "digests.db"
MD_DIR = DATA_DIR / "digests"

# La key vive SOLO en el .env del proyecto (gitignored): nunca hardcodeada,
# nunca en la config global de ZCode.
load_dotenv(PROJECT_ROOT / ".env")


def gemini_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or None


def gemini_models() -> list[str]:
    """Cadena de modelos a intentar en orden. GEMINI_MODEL fuerza uno solo;
    GEMINI_MODELS (coma-separado) redefine la cadena completa.

    gemini-2.5-* ya no acepta usuarios nuevos (404, sep-2026); 3.5-flash es el
    flash estable pero sufre picos de demanda (503), por eso hay fallbacks.
    """
    forced = os.environ.get("GEMINI_MODEL")
    if forced:
        return [forced.strip()]
    raw = os.environ.get("GEMINI_MODELS") or (
        "gemini-3.5-flash,gemini-3-flash-preview,gemini-flash-lite-latest"
    )
    return [m.strip() for m in raw.split(",") if m.strip()]


def max_output_tokens() -> int:
    return int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS") or "65536")
