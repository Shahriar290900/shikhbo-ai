"""
Gemini client — primary LLM for text chat + OCR fallback.

Roles:
  chat_stream()   — streaming text answers (primary when HF Space is sleeping)
  vision_ocr()    — image OCR + answer using Gemini File API (fallback for /vision)

Model: gemma-4-31b-it (same as original pipeline)
"""

import os
import tempfile
import base64
from typing import Generator

from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "models/gemma-4-31b-it"  # full path required by the API


def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=GEMINI_API_KEY)


# ── prompt builder (mirrors original prompts.py) ──────────────────────────────

_GROUNDING_NOTE = {
    "NCTB": "⚠️ পাঠ্যবই RAG লোড হচ্ছে — এটি সাধারণ জ্ঞান থেকে উত্তর।",
    "Edexcel_IAL": "⚠️ Textbook database loading — general knowledge answer below.",
    "default": "⚠️ Textbook database loading — general knowledge answer below.",
}

_MODE_SUFFIX = {
    "quiz":         "Generate 3-5 practice questions with answers.",
    "step_by_step": "Show a numbered step-by-step solution. Include formula, working, and units.",
    "simple":       "Use the simplest possible words. One idea at a time.",
    "normal":       "Be clear and conversational. Give a real-world example.",
}


def _build_system(curriculum: str, class_: str, subject: str, mode: str) -> str:
    is_bn = curriculum == "NCTB"
    lang = "Bengali" if is_bn else "English"
    mode_note = _MODE_SUFFIX.get(mode, _MODE_SUFFIX["normal"])
    note = _GROUNDING_NOTE.get(curriculum, _GROUNDING_NOTE["default"])

    if is_bn:
        return (
            f"{note}\n"
            f"তুমি {class_} পর্যায়ের {subject} বিষয়ের একজন সহায়ক শিক্ষক। "
            f"বাংলায় উত্তর দাও। {mode_note} শুধু সাধারণ বাংলায় লেখো।"
        )
    return (
        f"{note}\n"
        f"You are a helpful {class_} {subject} tutor ({curriculum}). "
        f"Answer in {lang}. {mode_note} Plain text only."
    )


# ── chat (streaming) ──────────────────────────────────────────────────────────

def chat_stream(
    query: str,
    curriculum: str,
    class_: str,
    subject: str,
    mode: str = "normal",
    history: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """Yields {status:...} then {chunk:...} dicts. No sources — no RAG."""
    try:
        client = _client()
    except RuntimeError as e:
        yield {"chunk": f"[Gemini not configured: {e}]"}
        return

    yield {"status": "thinking"}

    system = _build_system(curriculum, class_, subject, mode)

    contents: list[types.Content] = []
    if history:
        for msg in history[:-1]:
            role = "model" if msg.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=query)]))

    yield {"status": "generating answer"}

    try:
        stream = client.models.generate_content_stream(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                # Gemma 4 is a thinking model — budget for reasoning + answer
                max_output_tokens=4096,
            ),
        )
        for chunk in stream:
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                # Skip thought=True parts (internal reasoning chain) — only emit real answer
                if not part.thought and part.text:
                    yield {"chunk": part.text}
    except Exception as e:
        yield {"chunk": f"\n[Gemini error: {e}]"}


# ── OCR / vision ──────────────────────────────────────────────────────────────

def vision_ocr(
    image_base64: str,
    query: str,
    subject: str,
    curriculum: str,
    class_: str,
) -> dict:
    """
    Use Gemini's multimodal capability to OCR an image and answer the question.
    Returns {"extracted_text": ..., "answer": ..., "sources": [], "grounded": False}
    """
    try:
        client = _client()
    except RuntimeError as e:
        return {"error": str(e)}

    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        return {"error": "Invalid base64 image"}

    # Write to temp file so Gemini File API can upload it
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        uploaded = client.files.upload(file=tmp_path)
        lang_note = "বাংলায় উত্তর দাও।" if curriculum == "NCTB" else "Answer in English."
        prompt = (
            f"First, extract ALL text from this image (OCR). "
            f"Then answer this question based on the image content: {query}. "
            f"{lang_note} Begin your response with the extracted text on the first line, "
            f"then a blank line, then your answer."
        )
        resp = client.models.generate_content(
            model=MODEL,
            contents=[uploaded, types.Part(text=prompt)],
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=2048),
        )
        full = resp.text or ""
        parts = full.split("\n\n", 1)
        extracted = parts[0].strip()
        answer = parts[1].strip() if len(parts) > 1 else full.strip()

        return {
            "extracted_text": extracted,
            "answer": answer,
            "sources": [],
            "grounded": False,
        }
    except Exception as e:
        return {"error": f"Gemini vision error: {e}"}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
