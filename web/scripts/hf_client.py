"""
HF Space client with automatic Gemini fallback.

Primary:  HF Space /chat → Qwen2.5-VL-7B with FAISS RAG (textbook-grounded)
Fallback: Gemini gemma-4-31b-it (general knowledge, labeled clearly)

Primary:  HF Space /vision → Qwen2.5-VL OCR (best for Bengali + diagrams)
Fallback: Gemini File API vision
"""

import json
import os
import requests
from typing import Generator

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
COLD_START_TIMEOUT = 90  # seconds — T4 can take ~60s to wake


def _headers() -> dict:
    return {"Authorization": f"Bearer {HF_API_TOKEN}", "Content-Type": "application/json"}


# ── health ────────────────────────────────────────────────────────────────────

def health() -> dict:
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


def _hf_available() -> bool:
    """Quick liveness check — does NOT wake the space."""
    h = health()
    return h.get("status") in ("ok", "degraded")


# ── chat ──────────────────────────────────────────────────────────────────────

def chat_stream(
    query: str,
    curriculum: str,
    class_: str,
    subject: str,
    mode: str = "normal",
    history: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """
    Try HF Space first (RAG + Qwen). On any failure, fall back to Gemini.
    Yields {status:...}, {chunk:...}, {sources:[...]} dicts.
    """
    if HF_SPACE_URL and HF_API_TOKEN:
        yield from _hf_chat_stream(query, curriculum, class_, subject, mode)
        return

    # No HF Space configured — go straight to Gemini
    from scripts.gemini_client import chat_stream as gemini_stream
    yield from gemini_stream(query, curriculum, class_, subject, mode, history)


def _hf_chat_stream(
    query: str,
    curriculum: str,
    class_: str,
    subject: str,
    mode: str,
) -> Generator[dict, None, None]:
    """
    Calls HF Space /chat. On any error, falls back to Gemini automatically.
    """
    payload = {
        "query": query,
        "curriculum": curriculum,
        "class": class_,
        "subject": subject,
        "mode": mode,
    }

    yield {"status": "thinking"}

    hf_failed = False
    error_detail = ""

    try:
        resp = requests.post(
            f"{HF_SPACE_URL}/chat",
            headers=_headers(),
            json=payload,
            timeout=COLD_START_TIMEOUT,
        )

        if resp.status_code == 503:
            hf_failed = True
            error_detail = "sleeping"
        elif resp.status_code == 403:
            hf_failed = True
            error_detail = "auth"
        else:
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer", "")
            sources = data.get("sources", [])

            if not answer:
                hf_failed = True
                error_detail = "empty response"
            else:
                yield {"status": "synthesizing"}
                # Chunk the response for a smooth streaming feel
                words = answer.split(" ")
                buf = ""
                for i, w in enumerate(words):
                    buf += w + (" " if i < len(words) - 1 else "")
                    if len(buf) >= 40 or i == len(words) - 1:
                        yield {"chunk": buf}
                        buf = ""

                if sources:
                    yield {"sources": [
                        f"{s.get('chapter', '')} p.{s.get('page', '')}"
                        for s in sources
                    ]}
                return

    except requests.exceptions.Timeout:
        hf_failed = True
        error_detail = "timeout (model loading)"
    except Exception as e:
        hf_failed = True
        error_detail = str(e)[:80]

    if hf_failed:
        yield {"status": f"HF model {error_detail} — using Gemini fallback"}
        from scripts.gemini_client import chat_stream as gemini_stream
        # Skip the first {status} yield from gemini since we already sent one
        for payload in gemini_stream(query, curriculum, class_, subject, mode):
            if "status" not in payload:
                yield payload


# ── vision / OCR ──────────────────────────────────────────────────────────────

def vision_query(
    image_base64: str,
    query: str,
    subject: str,
    curriculum: str,
    class_: str,
) -> dict:
    """
    Try HF Space /vision (Qwen OCR). On failure, fall back to Gemini vision.
    Returns {"extracted_text": ..., "answer": ..., "sources": [...], "grounded": bool}
    """
    if not HF_SPACE_URL or not HF_API_TOKEN:
        # No HF Space — go directly to Gemini
        from scripts.gemini_client import vision_ocr
        return vision_ocr(image_base64, query, subject, curriculum, class_)

    payload = {
        "image_base64": image_base64,
        "query": query,
        "subject": subject,
        "curriculum": curriculum,
        "class": class_,
    }

    try:
        resp = requests.post(
            f"{HF_SPACE_URL}/vision",
            headers=_headers(),
            json=payload,
            timeout=COLD_START_TIMEOUT,
        )
        if resp.status_code in (503, 503):
            raise RuntimeError("HF vision endpoint unavailable")
        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        # Gemini fallback for OCR
        from scripts.gemini_client import vision_ocr
        result = vision_ocr(image_base64, query, subject, curriculum, class_)
        if "error" not in result:
            result["_fallback"] = "gemini"
        return result
