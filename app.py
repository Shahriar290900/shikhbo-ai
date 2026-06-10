"""
Shikhbo OCR Space — FastAPI service running on HuggingFace Docker GPU Space.

Endpoints:
    GET  /health  → readiness + CUDA status
    POST /ocr     → multipart: file (image) [+ instruction]; returns {"text": "..."}

Hardware: Nvidia T4 small (16 GB VRAM). Model: Qwen3-VL-4B-Instruct in bf16 (~10 GB).

Security: set OCR_API_KEY secret in Space → Settings → Secrets.
All callers must send header:  x-api-key: <OCR_API_KEY>

The Flask web backend (web/) calls this via scripts/ocr_client.py.
"""

import os
from io import BytesIO

import torch
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

# Qwen3-VL-4B fits a T4 (16 GB) in bf16 (~10 GB VRAM).
# Switch to Qwen/Qwen3-VL-8B-Instruct only if Bengali dense-text accuracy is short
# (requires a bigger GPU — at least 1xL4 24 GB).
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-VL-4B-Instruct")

# Shared secret. If set, callers must send: x-api-key: <value>
API_KEY = os.getenv("OCR_API_KEY")

DEFAULT_INSTRUCTION = (
    "Extract ALL text from this image exactly as written, preserving line "
    "breaks, math notation, and Bengali (Bangla) script. Do not translate, "
    "summarize, or add commentary. Output only the transcribed text."
)

app = FastAPI(title="Shikhbo OCR")
_processor = None
_model = None


@app.on_event("startup")
def load_model():
    global _processor, _model
    print(f"[startup] Loading {MODEL_ID} …")
    _processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    _model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    print(f"[startup] Model loaded. CUDA: {torch.cuda.is_available()}")


@app.get("/health")
def health():
    return {
        "status": "ok" if _model is not None else "loading",
        "model": MODEL_ID,
        "cuda": torch.cuda.is_available(),
    }


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    instruction: str = Form(DEFAULT_INSTRUCTION),
    x_api_key: str | None = Header(default=None),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    if _model is None:
        raise HTTPException(status_code=503, detail="Model still loading")

    raw = await file.read()
    try:
        image = Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image file")

    instruction = (instruction or DEFAULT_INSTRUCTION).strip()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": instruction},
            ],
        }
    ]

    inputs = _processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(_model.device)

    with torch.no_grad():
        generated = _model.generate(**inputs, max_new_tokens=2048, do_sample=False)

    trimmed = generated[:, inputs["input_ids"].shape[1]:]
    text = _processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]
    return {"text": text.strip()}
