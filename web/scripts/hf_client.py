"""
HF Space client.

Primary endpoints on HF Space (shahriarhameem/shikhbo-ai):
  POST /chat    — RAG-grounded text answers (Qwen2.5-VL + FAISS+BM25)
  POST /vision  — OCR + RAG answer from image (base64 JSON body)
  GET  /health  — {status, rag_loaded, llm_loaded, llm_failed, ...}

Auth: Authorization: Bearer <HF_API_TOKEN>

Two-tier routing:
  Text query  → Space /chat (RAG+LLM)  → Gemini fallback on 503/timeout
  Image query → Space /vision (VL+RAG) → Gemini vision_ocr() on 503/timeout
"""

import os
import requests
from typing import Generator

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

_TIMEOUT_CHAT = 120    # seconds — LLM inference can take a while
_TIMEOUT_HEALTH = 10


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json",
    }


# ── health ────────────────────────────────────────────────────────────────────

def health() -> dict:
    """Check if the Space is awake and what's loaded. Used by GET /api/health."""
    if not HF_SPACE_URL:
        return {"status": "not_configured"}
    try:
        r = requests.get(f"{HF_SPACE_URL}/health", timeout=_TIMEOUT_HEALTH)
        r.raise_for_status()
        data = r.json()
        # Normalise older format that only had {"status": "ok"|"loading"}
        if "rag_loaded" not in data:
            data["rag_loaded"] = data.get("status") == "ok"
            data["llm_loaded"] = data.get("status") == "ok"
        return data
    except requests.exceptions.Timeout:
        return {"status": "sleeping", "rag_loaded": False, "llm_loaded": False}
    except Exception as e:
        return {"status": "unreachable", "rag_loaded": False, "llm_loaded": False, "error": str(e)}


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
    Stream a text answer.
    Primary: HF Space /chat (RAG-grounded with textbook citations).
    Fallback: Gemini gemma-4-31b-it when Space returns 503 or times out.
    """
    if HF_SPACE_URL and HF_API_TOKEN:
        try:
            yield {"status": "retrieving from textbook"}
            payload = {
                "query": query,
                "curriculum": curriculum,
                "class": class_,
                "subject": subject,
                "mode": mode,
            }
            resp = requests.post(
                f"{HF_SPACE_URL}/chat",
                json=payload,
                headers=_headers(),
                timeout=_TIMEOUT_CHAT,
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                sources = data.get("sources", [])
                grounded = data.get("grounded", False)

                if grounded and sources:
                    yield {"status": "grounded", "sources": sources}

                # Word-chunk the synchronous answer to simulate streaming
                words = answer.split(" ")
                buf: list[str] = []
                for word in words:
                    buf.append(word)
                    if len(buf) >= 8:
                        yield {"chunk": " ".join(buf) + " "}
                        buf = []
                if buf:
                    yield {"chunk": " ".join(buf)}
                return

            # 503 = LLM not loaded yet or unavailable → fall through to Gemini
            # Any other non-200 also falls through
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            pass  # Space sleeping or unreachable
        except Exception:
            pass

    # Gemini fallback (gemma-4-31b-it via Google Gemini API)
    yield {"status": "AI tutor thinking"}
    from scripts.gemini_client import chat_stream as gemini_stream
    yield from gemini_stream(query, curriculum, class_, subject, mode, history)


# ── vision (image queries) ────────────────────────────────────────────────────

def vision_query(
    image_base64: str,
    query: str,
    subject: str,
    curriculum: str,
    class_: str,
) -> dict:
    """
    Send image to HF Space /vision for OCR + RAG-grounded answer.
    Returns {extracted_text, answer, sources, grounded}.
    Fallback to Gemini vision_ocr() on 503/timeout/error.
    """
    if HF_SPACE_URL and HF_API_TOKEN:
        try:
            payload = {
                "image_base64": image_base64,
                "query": query,
                "subject": subject,
                "curriculum": curriculum,
                "class": class_,
            }
            resp = requests.post(
                f"{HF_SPACE_URL}/vision",
                json=payload,
                headers=_headers(),
                timeout=_TIMEOUT_CHAT,
            )
            if resp.status_code == 200:
                return resp.json()
            # 503 = VL model not loaded → fall through
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            pass
        except Exception:
            pass

    # Gemini vision fallback
    from scripts.gemini_client import vision_ocr
    return vision_ocr(image_base64, query, subject, curriculum, class_)
