"""Client for the Shikhbo HuggingFace Space AI backend."""

import os
import json
import requests
from typing import Generator

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

_HEADERS = lambda: {"Authorization": f"Bearer {HF_API_TOKEN}", "Content-Type": "application/json"}

COLD_START_TIMEOUT = 120  # HF Spaces can take up to 2 min to wake up


def health() -> dict:
    """Check if the HF Space is up."""
    try:
        r = requests.get(f"{HF_SPACE_URL}/health", timeout=10)
        return r.json()
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


def chat_stream(
    query: str,
    curriculum: str,
    class_: str,
    subject: str,
    mode: str = "normal",
) -> Generator[dict, None, None]:
    """
    Yields status dicts then chunk dicts from the HF Space /chat endpoint.
    Falls back to an error message if the space is unavailable.
    """
    if not HF_SPACE_URL or not HF_API_TOKEN:
        yield {"chunk": "[HF Space not configured — set HF_SPACE_URL and HF_API_TOKEN]"}
        return

    payload = {
        "query": query,
        "curriculum": curriculum,
        "class": class_,
        "subject": subject,
        "mode": mode,
    }

    yield {"status": "thinking"}

    try:
        resp = requests.post(
            f"{HF_SPACE_URL}/chat",
            headers=_HEADERS(),
            json=payload,
            timeout=COLD_START_TIMEOUT,
        )
        if resp.status_code == 503:
            yield {"chunk": "⏳ The AI model is warming up — this can take up to 60 seconds on first use. Please try again in a moment."}
            return
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        sources = data.get("sources", [])

        yield {"status": "synthesizing"}
        # Simulate streaming by yielding words gradually
        words = answer.split(" ")
        buffer = ""
        for i, word in enumerate(words):
            buffer += word + (" " if i < len(words) - 1 else "")
            if len(buffer) >= 30 or i == len(words) - 1:
                yield {"chunk": buffer}
                buffer = ""

        if sources:
            yield {"sources": [f"{s.get('chapter', '')} p.{s.get('page', '')}" for s in sources]}

    except requests.exceptions.Timeout:
        yield {"chunk": "⏳ The AI is taking longer than expected. The model may be loading — please try again."}
    except Exception as e:
        yield {"chunk": f"[Connection error: {e}]"}


def vision_query(
    image_base64: str,
    query: str,
    subject: str,
    curriculum: str,
    class_: str,
) -> dict:
    """Call the HF Space /vision endpoint (synchronous)."""
    if not HF_SPACE_URL or not HF_API_TOKEN:
        return {"error": "HF Space not configured"}

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
            headers=_HEADERS(),
            json=payload,
            timeout=COLD_START_TIMEOUT,
        )
        if resp.status_code == 503:
            return {"error": "Vision endpoint not available (GPU required)"}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
