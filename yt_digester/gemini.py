"""Video de YouTube → texto completo, vía Gemini multimodal por URL.

Patrón portado de knowledge-generator/scripts/gemini_video.py: FileData con la
URL pública (Gemini "ve" audio+imagen, no descargamos nada), response_schema
JSON estricto, temperature 0.2, thinking_budget=0 (evita que el "thinking" se
coma el presupuesto y trunque el JSON), preflight del modelo y 1 reintento.
"""

from __future__ import annotations

import json
import time

from . import config

# Schema genérico del digest (independiente del dominio).
DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "channel": {"type": "string"},
        "language": {"type": "string"},
        "duration_s": {"type": "integer"},
        "full_text": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "full_text", "summary", "key_points", "language"],
}


def build_prompt(language: str | None = None) -> str:
    text_lang = (
        f"Write `full_text` in the video's original language." if not language
        else f"Write `full_text` in {language}."
    )
    return (
        "Watch this YouTube video (audio + visuals) from start to end and turn "
        "it into a complete written version of its content.\n\n"
        "Fill:\n"
        "- title: the actual subject covered (not clickbait).\n"
        "- channel: the channel name if identifiable.\n"
        "- language: source language of the video (ISO code like 'en', 'es').\n"
        "- duration_s: approximate duration in seconds.\n"
        f"- full_text: an EXHAUSTIVE, faithful rendering of EVERYTHING the video "
        f"communicates, in chronological order: all spoken content transcribed in "
        f"flowing prose, plus any substantive on-screen content (slides, diagrams, "
        f"code, demonstrations) described where it occurs. This is the full "
        f"reading material: do not shorten, skip, or summarize sections. "
        f"{text_lang}\n"
        "- summary: 2-5 sentences in SPANISH summarizing what the video covers.\n"
        "- key_points: the concrete factual takeaways (concepts, steps, gotchas), "
        "in the video's language.\n"
        "- topics: 2-6 short kebab-case labels (e.g. 'error-handling').\n"
        "Be faithful to the video; do not invent facts it does not contain. If "
        "the video has no speech, describe the visuals in detail."
    )


def digest_video(url: str, language: str | None = None) -> dict:
    """Pasa la URL pública a Gemini y devuelve el dict del digest (+ clave
    `model` con el modelo que lo produjo).

    Intenta la cadena de modelos de config en orden: salta al siguiente si el
    modelo no existe (404) o está saturado (503). Lanza RuntimeError con
    mensaje legible si falta la key o ningún modelo pudo procesar el video.
    """
    api_key = config.gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "falta GEMINI_API_KEY: copia .env.example a .env y pon tu key de "
            "https://aistudio.google.com/apikey"
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai no está instalado (pip install -r requirements.txt)"
        ) from e

    client = genai.Client(api_key=api_key)
    contents = types.Content(parts=[
        types.Part(file_data=types.FileData(file_uri=url)),
        types.Part(text=build_prompt(language)),
    ])

    failures = []
    for attempt in range(2):  # 2 rondas con espera: los picos 503 suelen durar poco
        for model in config.gemini_models():
            if not _ping(client, model, types):
                failures.append(f"{model}: no disponible (404/503)")
                continue
            result, err = _generate(client, model, types, contents)
            if result is not None:
                if not result.get("full_text", "").strip():
                    failures.append(f"{model}: digest sin texto")
                    continue
                result["model"] = model
                return result
            failures.append(f"{model}: {err}")
        if attempt == 0:
            time.sleep(20)
    saturated = all("503" in f for f in failures)
    hint = ("todos los modelos están saturados (503); reintenta en unos "
            "minutos. " if saturated else "")
    raise RuntimeError(
        f"ningún modelo de Gemini pudo procesar el video (¿es público?). {hint}"
        + "; ".join(failures)
    )


def _generate(client, model: str, types, contents) -> tuple[dict | None, str | None]:
    """Una corrida real con 1 reintento si el JSON viene truncado/inválido.

    Devuelve (result|None, error|None). Errores de API (404/503/429...) no se
    reintentan aquí: el SDK ya reintentó internamente, así que se devuelve el
    error para que la cadena pruebe el siguiente modelo.
    """
    last_err = None
    for _attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=_gen_config(types)
            )
            return json.loads(resp.text), None
        except json.JSONDecodeError as e:
            last_err = f"JSON inválido/truncado: {e}"
        except Exception as e:  # noqa: BLE001 — error de API: siguiente modelo
            return None, str(e)[:200]
    return None, last_err


def _gen_config(types):
    # max_output_tokens al máximo + thinking_budget=0: en flash el "thinking"
    # se comía el presupuesto y truncaba el JSON en videos largos (lección
    # de knowledge-generator). Aquí el texto completo necesita todo el margen.
    kwargs = dict(
        response_mime_type="application/json",
        response_schema=DIGEST_SCHEMA,
        temperature=0.2,
        max_output_tokens=config.max_output_tokens(),
    )
    try:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    except Exception:  # noqa: BLE001 — versiones sin ThinkingConfig
        pass
    return types.GenerateContentConfig(**kwargs)


def _ping(client, model: str, types) -> bool:
    """Valida el modelo con una llamada mínima ANTES de gastar la corrida real.

    False si el modelo no existe o está saturado (la cadena probará el
    siguiente); True si responde.
    """
    try:
        client.models.generate_content(
            model=model,
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=8),
        )
        return True
    except Exception:  # noqa: BLE001 — 404/503/429: no insiste con este modelo
        return False
