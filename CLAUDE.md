# CLAUDE.md — Shikhbo (শিখবো) Project Instructions
## Multimodal AI Educational Assistant · THE INFINITY AI BUILDFEST 2026 · EdTech Track

This file governs how Claude (Claude Code) behaves while building, refactoring, and deploying Shikhbo. Read it fully before any task.

---

## PROJECT IDENTITY

**Shikhbo** is a privacy-first, curriculum-aligned, multimodal AI learning assistant for Bangladeshi students. It answers grounded in verified textbook data — never generic AI guesses. It supports text, voice (STT + TTS), and image (OCR) interaction in both Bengali and English.

**Retrieval corpus (grounding sources):**
- NCTB SSC ICT textbook chunks (`ICT_C1.jsonl`, Bengali)
- Edexcel IAL Astrophysics chunks (`Astrophysics_Cosmology_RAG.jsonl`, English)
- Edexcel Astrophysics revision notes PDF (`Astrophysics_Cosmology_Notes.pdf`) — chunk this and add to the corpus; it contains worked examples, key terms, and exam practice Q&A that are ideal grounding material, especially for the Step-by-Step mode and for checking student answers against worked solutions.

**Demo scope (focus subjects):**
- **NCTB curriculum:** SSC ICT (Bengali-language content)
- **Edexcel International A-Level:** Physics — Astrophysics & Cosmology chapter (English content)

**Two-tier product:**
- **Free / self-hosted tier:** Text + voice RAG answering, running entirely on our own rented GPU with no external API calls. Grounded in textbook chunks.
- **Premium / cloud tier:** Adds image/file upload analysis (vision OCR), Bengali text-to-speech, a stronger LLM, and higher rate limits.

---

## CORE BEHAVIORAL DIRECTIVES FOR CLAUDE

1. **Ground first, then fall back gracefully.** Always attempt to answer from retrieved context (the chunked JSONL data + the Astrophysics notes PDF + ICT textbook chunks). Two cases:
   - **Found in textbook:** Answer grounded in the retrieved chunks, with a citation (chapter + page). This is the primary, trusted path.
   - **NOT found above the confidence threshold:** Do NOT hallucinate a textbook citation. Instead, respond with a clear two-part answer: (a) an explicit notice — "এই প্রশ্নের উত্তর তোমার পাঠ্যবইয়ে সরাসরি পাইনি / I couldn't find this directly in your textbook," then (b) a helpful, simple, general explanation of the concept clearly labeled as a general explanation, not a textbook citation. The label is mandatory so students always know which answers are textbook-grounded and which are general knowledge.

2. **Citations are mandatory.** Every generated answer must reference the source `chunk_id`, mapped to a human-readable chapter + page. This is the product's entire trust proposition.

3. **Curriculum isolation is non-negotiable.** Before any semantic search, hard-filter the vector store by the user's `curriculum`, `subject`, and `class`. An SSC ICT student must never receive Edexcel Astrophysics chunks, and vice versa. This is a correctness requirement, not an optimization.

4. **Bengali quality is the differentiator.** When working on the NCTB/ICT path, treat Bengali fluency and accuracy as a first-class requirement. Do not assume a model handles Bengali well — flag for evaluation.

5. **Be honest about feasibility.** When asked to implement something that is technically unrealistic in scope or timeframe (e.g., on-device offline inference of a 7B model on a low-end phone, accurate handwritten-Bengali OCR), say so directly and propose the achievable alternative.

6. **Cost-aware by default.** Prefer scale-to-zero GPU endpoints, consolidated model hosting, and CPU for embeddings/BM25 where viable. Never propose always-on multi-GPU architectures for a prototype without flagging the cost.

7. **Respond with working code, not pseudo-code.** This project deploys for real. Provide complete, runnable implementations with error handling, not sketches. When editing existing files, preserve the existing structure (Flask app, scripts/pipeline, etc.).

8. **Privacy-first.** Uploaded images/PDFs are processed in isolation and discarded post-transaction (per README). Never log raw student content. No student data used for training without explicit consent.

---

## CORRECTED TECH STACK (supersedes README where conflicting)

### Language Models
- **Premium answering LLM:** `Qwen/Qwen2.5-7B-Instruct` (Apache 2.0) OR `google/gemma-2-9b-it` — chosen via Bengali eval, NOT defaulted to Gemma-2-2B
- **Free/offline-tier LLM:** `gemma2:2b` via Ollama (fallback only — acceptable lower quality)
- **Complex reasoning (Astrophysics calculations):** optionally `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` (MIT)

### Vision / OCR
- **English + math + diagrams:** `Qwen/Qwen2.5-VL-7B-Instruct` (Apache 2.0)
- **Printed Bengali:** PaddleOCR Bengali model + Qwen2.5-VL cross-check
- **Handwritten Bengali:** EXPERIMENTAL — do not promise accuracy
- **DeepSeek is NOT used for OCR** (no production vision OCR model)

### Retrieval (RAG)
- **Embeddings:** `BAAI/bge-m3` (multilingual — handles Bengali + English)
- **Dense store:** FAISS (CPU)
- **Sparse:** BM25 via rank-bm25 — MUST use a Bengali-aware tokenizer for Bengali content, not whitespace split
- **Fusion:** Reciprocal Rank Fusion (RRF), weights tuned separately per language
- **Reranker:** `BAAI/bge-reranker-v2-m3`

### Speech
- **STT:** Faster-Whisper (supports Bengali + English — validate Bengali accuracy)
- **TTS (English, all tiers):** Piper `en_US-lessac-medium`
- **TTS (Bengali, premium only):** Coqui TTS Bengali or Google Cloud TTS bn-IN. Free tier: espeak-ng Bengali clearly labeled as robotic, or English only.

### Backend & Infra
- **API:** Flask (existing) — keep unless a migration is explicitly requested
- **Auth/profiles DB:** MySQL (existing) — store user `curriculum`, `class`, `subject`, tier
- **Subscription/billing:** Stripe (new — premium tier gating)
- **Model serving:** consolidated GPU box (embeddings + reranker + LLM together); vision as separate scale-to-zero endpoint
- **GPU hosting:** RunPod / Vast.ai on-demand or HF Inference Endpoints with scale-to-zero. NOT always-on HF Spaces persistent GPU.
- **Object storage:** Cloudflare R2 or S3 for transient uploads (auto-delete post-processing)

### Frontend
- Vanilla JS / HTML / CSS (existing) — keep unless React migration is requested

---

## UNIFIED CHUNK SCHEMA (normalize ALL data to this)

Both `ICT_C1.jsonl` and `Astrophysics_Cosmology_RAG.jsonl` must be normalized to this single schema before embedding:

```json
{
  "chunk_id": "string — unique, e.g. SSC-ICT-C1-P1-CH1",
  "curriculum": "NCTB | Edexcel_IAL",
  "class": "SSC | A-level",
  "subject": "ICT | Physics",
  "language": "bn | en",
  "chapter_no": "string",
  "chapter_title": "string — normalized field name (was chapter_name in Astro file)",
  "page_no": "integer",
  "topic": "string",
  "spec_ref": "string | null — populated for Edexcel, null for NCTB",
  "prerequisite": "string | null",
  "keywords": ["array — populate even for ICT (currently empty)"],
  "token_count": "integer",
  "content": "string — the chunk text",
  "embedding_vector": "null until ingestion computes it"
}
```

**Migration tasks:**
- Rename `chapter_name` → `chapter_title` in the Astrophysics file
- Add `curriculum` and `language` to every chunk
- Backfill `keywords` for ICT chunks (extract from content)
- Add `spec_ref: null` to ICT chunks for schema consistency

---

## RAG PIPELINE — REQUIRED FLOW

```
User query + profile (curriculum, class, subject)
        │
        ▼
HARD FILTER vector store: WHERE curriculum=? AND subject=? AND class=?
        │
        ▼
Dense search (FAISS, bge-m3)  +  Sparse search (BM25, language-aware tokenizer)
        │
        ▼
Reciprocal Rank Fusion (RRF) — language-tuned weights
        │
        ▼
Rerank top candidates (bge-reranker-v2-m3)
        │
        ▼
Confidence gate: if top score < threshold → "Not found in textbook" response
        │
        ▼
Build grounded prompt with retrieved chunks + citations
        │
        ▼
Generate (Qwen2.5-7B / Gemma-9B premium · gemma2:2b free)
        │
        ▼
Stream answer + cite chunk_id → chapter + page
```

---

## LEARNING MODES (from the presentation — implement all three)
- **Simple:** concept-building, plain-language explanation grounded in textbook
- **Quiz:** generate self-assessment questions from the retrieved chapter content
- **Step-by-Step:** structured problem solving (essential for Astrophysics calculations — show formula, substitution, units, answer)

The mode is a prompt-template switch, all sharing the same retrieved context.

---

## SUBSCRIPTION / TIER GATING

| Feature | Free (self-hosted) | Premium (cloud) |
|---|---|---|
| Text RAG answering | ✅ | ✅ |
| Voice STT input | ✅ | ✅ |
| English TTS output | ✅ | ✅ |
| Bengali TTS output | ❌ (or robotic espeak) | ✅ (Coqui/Google) |
| Image/PDF upload (OCR) | ❌ | ✅ |
| LLM quality | gemma2:2b | Qwen2.5-7B / Gemma-9B |
| Rate limit | low | high |

Enforce tier server-side via the user's MySQL profile before serving any premium feature. Never gate only on the frontend.

---

## DEPLOYMENT PRINCIPLES (revised for $10 budget, demo June 11-12)
- **Run the core stack locally on the Mac via Ollama — costs $0.** LLM, bge-m3 embeddings, bge-reranker, FAISS, BM25, Faster-Whisper STT, Piper TTS, Flask, MySQL all run on the Mac.
- **The only potential cost is the premium vision/OCR feature.** Prefer `qwen2.5vl:3b` locally ($0); optionally rent an L4/A10G GPU for demo hours only (~$0.40/hr, ≤$6 total) if 7B vision quality is needed for judges.
- Always-on cloud GPU is forbidden for this prototype — it would exhaust $10 in hours.
- Co-locate models; do NOT run separate Spaces per model.
- If renting GPU for vision: spin up 1 hour before demo, spin DOWN immediately after each session. Set a billing alert at $8.
- Local-first is also more reliable for a live demo — no network dependency, no cold-start latency mid-presentation.

---

## WHEN STARTING ANY TASK, CLAUDE SHOULD
1. Confirm which curriculum path the task affects (NCTB/ICT-Bengali vs Edexcel/Astro-English) — they have different language and quality requirements
2. Confirm which tier (free self-hosted vs premium cloud) the feature belongs to
3. State any feasibility concern up front before writing code
4. Write complete, runnable code preserving the existing Flask/scripts structure
5. Include citation logic in any answer-generation code
6. Flag GPU cost implications of any infrastructure change
