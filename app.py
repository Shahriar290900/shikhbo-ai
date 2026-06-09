"""
app.py — Shikhbo FastAPI backend.

Endpoints:
  POST /chat   — RAG-grounded answer generation
  POST /vision — OCR + RAG (GPU only; returns 503 on CPU Space)
  GET  /health — liveness check

Run locally (after ingest.py):
  uvicorn app:app --host 0.0.0.0 --port 7860

Required env vars:
  API_TOKEN           — Bearer token checked on every request
  LLM_MODEL           — HF model ID (default: Qwen/Qwen2.5-1.5B-Instruct)
  LLM_DEVICE          — "cpu" | "cuda" (default: cpu)
  MAX_NEW_TOKENS      — int (default: 512)
  CONFIDENCE_THRESHOLD— float (default: 0.3)
  VISION_ENABLED      — "true" | "false" (default: false)
"""

import base64
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ── env ───────────────────────────────────────────────────────────────────────

API_TOKEN = os.environ.get("API_TOKEN", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
LLM_DEVICE = os.environ.get("LLM_DEVICE", "cpu")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "512"))
VISION_ENABLED = os.environ.get("VISION_ENABLED", "false").lower() == "true"

# ── startup / shutdown ────────────────────────────────────────────────────────

_state: dict[str, Any] = {"rag": None, "llm": None, "vision_model": None}
_llm_lock = threading.Lock()


def _ensure_llm_loaded() -> None:
    if _state["llm"] is not None:
        return
    with _llm_lock:
        if _state["llm"] is not None:
            return
        for attempt in range(1, 4):
            try:
                print(f"Loading LLM: {LLM_MODEL} on {LLM_DEVICE}… (attempt {attempt}/3)")
                import torch
                from transformers import pipeline
                if LLM_DEVICE == "cpu":
                    pipe = pipeline(
                        "text-generation",
                        model=LLM_MODEL,
                        device=-1,
                        torch_dtype=torch.float32,
                        trust_remote_code=True,
                    )
                else:
                    pipe = pipeline(
                        "text-generation",
                        model=LLM_MODEL,
                        device_map="auto",
                        torch_dtype="auto",
                        trust_remote_code=True,
                    )
                _state["llm"] = pipe
                print(f"LLM loaded: {LLM_MODEL}")
                return
            except Exception as exc:
                if attempt == 3:
                    print(f"[error] LLM failed after 3 attempts: {exc}")
                    return
                print(f"[warn] LLM attempt {attempt} failed: {exc}. Retrying in 10s…")
                time.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ingest import run_ingest
    run_ingest()

    from rag import ShikhboRAG
    _state["rag"] = ShikhboRAG()
    # LLM and reranker load lazily on first /chat request

    yield

    _state["rag"] = None
    _state["llm"] = None
    _state["vision_model"] = None


app = FastAPI(title="Shikhbo AI Backend", version="1.0.0", lifespan=lifespan)

# ── auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer()


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    if not API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_TOKEN env var not set on server",
        )
    if creds.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token",
        )


# ── schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    curriculum: str
    class_: str = Field(alias="class")
    subject: str
    mode: str = "normal"   # normal | simple | quiz | step_by_step
    quality: str = "fast"  # fast | enhanced (single model loaded; logged only)

    model_config = {"populate_by_name": True}


class Source(BaseModel):
    chunk_id: str
    chapter: str
    chapter_no: str
    page: int


class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    answer: str
    sources: list[Source]
    grounded: bool
    model_used: str


class VisionRequest(BaseModel):
    image_base64: str
    query: str
    subject: str
    curriculum: str
    class_: str = Field(alias="class", default="")

    model_config = {"populate_by_name": True}


class VisionResponse(BaseModel):
    extracted_text: str
    answer: str
    sources: list[Source]
    grounded: bool


# ── prompt templates ──────────────────────────────────────────────────────────

def _build_system_prompt(curriculum: str, mode: str, grounded: bool) -> str:
    is_bengali = curriculum == "NCTB"

    if not grounded:
        if is_bengali:
            return (
                "তুমি শিক্ষার্থীদের জন্য একজন সহায়ক শিক্ষক। "
                "পাঠ্যবইয়ে এই প্রশ্নের উত্তর সরাসরি পাওয়া যায়নি, তাই "
                "একটি সাধারণ ব্যাখ্যা দাও এবং উত্তরের শুরুতে স্পষ্টভাবে বলো: "
                "\"এই প্রশ্নের উত্তর তোমার পাঠ্যবইয়ে সরাসরি পাইনি। নিচের ব্যাখ্যাটি সাধারণ জ্ঞান থেকে:\""
            )
        return (
            "You are a helpful tutor. The answer to this question was not found "
            "directly in the textbook. Provide a clear general explanation and "
            "begin your answer with exactly: "
            "\"I couldn't find this directly in your textbook. The following is a general explanation:\""
        )

    if mode == "simple":
        if is_bengali:
            return (
                "তুমি একজন বন্ধুত্বপূর্ণ শিক্ষক। নিচের পাঠ্যবইয়ের অংশ ব্যবহার করে "
                "সহজ ভাষায় ধারণাটি ব্যাখ্যা করো। পরিভাষা কম ব্যবহার করো, "
                "বাস্তব উদাহরণ দাও, এবং উত্তরের শেষে সূত্র উল্লেখ করো।"
            )
        return (
            "You are a friendly tutor. Using the textbook passages below, "
            "explain the concept in plain language. Avoid jargon, use real-world "
            "analogies where helpful, and cite the source at the end."
        )

    if mode == "quiz":
        if is_bengali:
            return (
                "তুমি একজন পরীক্ষা-প্রস্তুতি সহকারী। নিচের পাঠ্যবইয়ের অংশ থেকে "
                "৩–৫টি সংক্ষিপ্ত প্রশ্ন তৈরি করো (MCQ বা সংক্ষিপ্ত উত্তর)। "
                "প্রতিটি প্রশ্নের নিচে সঠিক উত্তর এবং পাঠ্যবইয়ের রেফারেন্স দাও।"
            )
        return (
            "You are an exam-prep assistant. Using the textbook passages below, "
            "generate 3–5 self-assessment questions (MCQ or short-answer). "
            "Include the correct answer and textbook reference below each question."
        )

    if mode == "step_by_step":
        if is_bengali:
            return (
                "তুমি একজন গণিত ও বিজ্ঞান টিউটর। ধাপে ধাপে সমাধান দাও: "
                "সূত্র → প্রতিস্থাপন → একক → চূড়ান্ত উত্তর। "
                "পাঠ্যবইয়ের অংশ থেকে প্রাসঙ্গিক তথ্য ব্যবহার করো।"
            )
        return (
            "You are a maths/science tutor. Show a structured solution: "
            "Formula → Substitution → Units → Final Answer. "
            "Use relevant information from the textbook passages provided."
        )

    # default: normal
    if is_bengali:
        return (
            "তুমি একজন পাঠ্যবই-ভিত্তিক শিক্ষক। নিচের পাঠ্যবইয়ের অংশ ব্যবহার করে "
            "প্রশ্নের উত্তর দাও। উত্তরে অধ্যায় ও পৃষ্ঠা নম্বর উল্লেখ করো।"
        )
    return (
        "You are a textbook-grounded tutor. Answer using the passages below. "
        "Reference the chapter and page number in your answer."
    )


def _build_user_prompt(
    query: str,
    chunks: list[dict],
    curriculum: str,
    grounded: bool,
) -> str:
    if not grounded or not chunks:
        return query

    is_bengali = curriculum == "NCTB"
    sep = "\n---\n"
    passages = sep.join(
        f"[{c['chunk_id']} | {c.get('chapter_title', '')} p.{c.get('page_no', '?')}]\n{c['content']}"
        for c in chunks
    )
    if is_bengali:
        return f"পাঠ্যবইয়ের অংশ:\n{passages}\n\nপ্রশ্ন: {query}"
    return f"Textbook passages:\n{passages}\n\nQuestion: {query}"


# ── LLM generation ────────────────────────────────────────────────────────────

def _generate(system: str, user: str) -> str:
    llm = _state["llm"]
    if llm is None:
        return "[LLM not loaded — check server logs]"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        out = llm(
            messages,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.3,
            return_full_text=False,
        )
        # pipeline returns list of dicts; extract generated text
        if isinstance(out, list) and out:
            item = out[0]
            if isinstance(item, dict):
                generated = item.get("generated_text", "")
                if isinstance(generated, list) and generated:
                    return generated[-1].get("content", str(generated))
                return str(generated)
        return str(out)
    except Exception as exc:
        return f"[Generation error: {exc}]"


# ── /chat endpoint ────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_token)])
def chat(req: ChatRequest) -> ChatResponse:
    rag = _state["rag"]
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG not initialised")

    _ensure_llm_loaded()

    try:
        chunks, grounded = rag.retrieve(
            query=req.query,
            curriculum=req.curriculum,
            subject=req.subject,
            class_=req.class_,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    system_prompt = _build_system_prompt(req.curriculum, req.mode, grounded)
    user_prompt = _build_user_prompt(req.query, chunks, req.curriculum, grounded)
    answer = _generate(system_prompt, user_prompt)

    sources = [Source(**s) for s in rag.format_sources(chunks)]

    return ChatResponse(
        answer=answer,
        sources=sources,
        grounded=grounded,
        model_used=LLM_MODEL,
    )


# ── /vision endpoint ──────────────────────────────────────────────────────────

@app.post("/vision", response_model=VisionResponse, dependencies=[Depends(verify_token)])
def vision(req: VisionRequest) -> VisionResponse:
    if not VISION_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Vision requires GPU tier. Set VISION_ENABLED=true on a GPU Space.",
        )

    # lazy-load vision model
    if _state["vision_model"] is None:
        print("Lazy-loading Qwen2.5-VL-7B-Instruct…")
        try:
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
            _state["vision_model"] = {
                "model": Qwen2VLForConditionalGeneration.from_pretrained(
                    "Qwen/Qwen2.5-VL-7B-Instruct",
                    torch_dtype="auto",
                    device_map=LLM_DEVICE,
                    trust_remote_code=True,
                ),
                "processor": AutoProcessor.from_pretrained(
                    "Qwen/Qwen2.5-VL-7B-Instruct", trust_remote_code=True
                ),
            }
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Vision model load failed: {exc}")

    vm = _state["vision_model"]
    model = vm["model"]
    processor = vm["processor"]

    # decode and save image to a temp file
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        from PIL import Image
        image = Image.open(tmp_path).convert("RGB")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": (
                            f"Extract all text from this image. "
                            f"Then answer: {req.query}"
                        ),
                    },
                ],
            }
        ]
        text_input = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = processor(text=[text_input], images=[image], return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        import torch
        with torch.no_grad():
            generated_ids = model.generate(**inputs, max_new_tokens=512)
        generated_ids_trimmed = [
            out[len(in_ids):]
            for in_ids, out in zip(inputs["input_ids"], generated_ids)
        ]
        raw_output = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True
        )[0]

        # split: assume first paragraph = extracted text, rest = answer
        parts = raw_output.split("\n\n", 1)
        extracted_text = parts[0].strip()
        ocr_answer = parts[1].strip() if len(parts) > 1 else raw_output.strip()

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vision processing error: {exc}")
    finally:
        import os as _os
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass

    # run RAG on extracted text + query
    rag = _state["rag"]
    combined_query = f"{extracted_text}\n\n{req.query}".strip()
    try:
        chunks, grounded = rag.retrieve(
            query=combined_query,
            curriculum=req.curriculum,
            subject=req.subject,
            class_=req.class_,
        )
    except ValueError:
        chunks, grounded = [], False

    sources = [Source(**s) for s in rag.format_sources(chunks)]

    return VisionResponse(
        extracted_text=extracted_text,
        answer=ocr_answer,
        sources=sources,
        grounded=grounded,
    )


# ── /health endpoint ──────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "rag_loaded": _state["rag"] is not None,
        "llm_loaded": _state["llm"] is not None,
        "model": LLM_MODEL,
    }
