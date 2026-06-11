"""
HF Space client.

The HF Space (shahriarhameem/shikhbo-ai) is now an OCR-only service.
  - Image OCR  → scripts/ocr_client.py  (calls Space /ocr directly)
  - Text chat  → scripts/gemini_client.py  (Gemma 4 31B via Gemini API)

This module now only exposes:
  health()       — liveness check used by GET /api/health
  chat_stream()  — delegates directly to Gemini (no HF Space chat endpoint)
"""

import os
import requests
from typing import Generator

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")


# ── health ────────────────────────────────────────────────────────────────────

def health() -> dict:
    """Check if the OCR Space is awake. Used only for GET /api/health."""
    if not HF_SPACE_URL:
        return {"status": "not_configured"}
    try:
        r = requests.get(f"{HF_SPACE_URL}/health", timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"status": "sleeping"}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


# ── chat (text queries) ───────────────────────────────────────────────────────

def chat_stream(
    query: str,
    curriculum: str,
    class_: str,
    subject: str,
    mode: str = "normal",
    history: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """
    Stream a text answer via Gemma 4 31B (Gemini API).
    Yields {status:...}, {chunk:...} dicts.
    The HF Space is OCR-only — text generation always uses Gemini.
    """
    from scripts.gemini_client import chat_stream as gemini_stream
    yield from gemini_stream(query, curriculum, class_, subject, mode, history)
