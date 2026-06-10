"""
scripts/ocr_client.py — calls the Shikhbo OCR Docker Space (FastAPI + Qwen3-VL).

The Space is a Docker SDK Space serving FastAPI on the T4 GPU.
We call it over plain HTTP (not gradio_client) with a multipart image upload.

When the Space is sleeping, the first request triggers a restart (~60s cold start).
On timeout or any error, ocr_image() returns "" so the pipeline continues without OCR.

Env vars:
    HF_SPACE_URL   base URL of the Space (default: https://shahriarhameem-shikhbo-ai.hf.space)
    OCR_API_KEY    shared secret that must match the Space's OCR_API_KEY secret
"""

import logging
import os

import requests

_BASE_URL = os.getenv("HF_SPACE_URL", "https://shahriarhameem-shikhbo-ai.hf.space").rstrip("/")
_OCR_URL = f"{_BASE_URL}/ocr"
_OCR_API_KEY = os.getenv("OCR_API_KEY", "")

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
_log = logging.getLogger(__name__)


def is_image(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in _IMAGE_EXTS


def ocr_image(file_path: str, instruction: str | None = None, timeout: int = 120) -> str:
    """Return extracted text from image, or '' on any failure (never raises)."""
    if not file_path or not os.path.isfile(file_path) or not is_image(file_path):
        return ""

    headers = {}
    if _OCR_API_KEY:
        headers["x-api-key"] = _OCR_API_KEY

    data = {"instruction": instruction} if instruction else {}

    try:
        with open(file_path, "rb") as fh:
            resp = requests.post(
                _OCR_URL,
                files={"file": (os.path.basename(file_path), fh)},
                data=data,
                headers=headers,
                timeout=timeout,
            )
        resp.raise_for_status()
        return (resp.json().get("text") or "").strip()
    except Exception as exc:
        _log.warning("OCR call failed (%s): %s", file_path, exc)
        return ""
