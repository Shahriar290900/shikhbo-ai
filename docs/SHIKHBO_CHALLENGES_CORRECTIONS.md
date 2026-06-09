# Shikhbo — Critical Corrections & Challenges
## Read this BEFORE you build further

---

## 🔴 SEVERITY: CRITICAL (will break the demo if ignored)

### 1. Gemma 2 (2B) is weak at Bengali — your core value prop is at risk
Gemma 2 2B was not trained with strong Bengali coverage. For a Bengali-first educational assistant grounded in NCTB textbooks, a 2B model will produce grammatically awkward, sometimes factually drifting Bengali. This is the single biggest risk to your demo because Bengali quality IS the differentiator.

**Options, best to worst for your case:**
- **Best:** `google/gemma-2-9b-it` — meaningfully better Bengali, needs ~18GB VRAM (fits on rented A10G/L4/A100)
- **Strong alternative:** `Qwen/Qwen2.5-7B-Instruct` — surprisingly decent Bengali, Apache 2.0, and you're already using Qwen for vision so one model family simplifies ops
- **Bengali-specialized:** Check `BanglaLLM` / `titulm` Bengali fine-tunes on HF — variable quality, test before committing
- **Keep Gemma 2 2B only as the offline/free-tier fallback**, not the premium experience

**Action:** Run a 20-question Bengali ICT eval across Gemma-2-2B, Gemma-2-9B, and Qwen2.5-7B before deciding. Don't lock the model from the README's 2B choice.

### 2. Bengali OCR is the hardest unsolved piece — neither DeepSeek nor most VLMs handle Bangla script well
You mentioned "Qwen or DeepSeek" for OCR. Reality check:
- **DeepSeek has no production-grade vision OCR model** — drop this idea.
- **Qwen2.5-VL** handles printed Bengali poorly and handwritten Bengali very poorly. English/math it does well.
- **PaddleOCR** (already in your stack) has a Bengali model but accuracy on real student photos (angled, low light, handwriting) drops sharply.

**Recommended split:**
- **English + math + diagrams (Astrophysics):** Qwen2.5-VL-7B — works well
- **Printed Bengali (ICT textbook photos):** PaddleOCR Bengali model + Qwen2.5-VL as cross-check
- **Handwritten Bengali:** flag as experimental — do NOT promise accuracy in the demo

**Action:** Test Bengali OCR on 10 real phone photos of an ICT page early. If accuracy is low, scope the demo to printed-text and English-handwriting only, and present Bengali handwriting as "roadmap."

### 3. Bengali TTS gap — Piper's `en_US-lessac-medium` is English-only
Your README lists Piper with an English voice. You cannot read Bengali answers aloud with an English voice model. Bengali Piper voices are scarce and low quality.

**Options:**
- **Coqui TTS** Bengali models, or
- **Google Cloud TTS** (bn-IN voices, paid, cloud-only — fits your premium tier), or
- **espeak-ng** Bengali (robotic but offline-capable for free tier)

**Action:** Bengali TTS goes in the premium/cloud tier using a real service. Free/offline tier: English TTS only, or robotic espeak Bengali clearly labeled.

---

## 🟠 SEVERITY: HIGH (architecture decisions you must make now)

### 4. "Offline on student device" is likely infeasible — clarify what offline means
Running Gemma 2B + bge-m3 embeddings + bge-reranker + FAISS locally needs ~6-8GB RAM and ideally a GPU. Typical low-resource student devices (entry Android phones, old laptops) cannot run this. If "offline" means "runs on your server without calling external APIs," that's achievable. If it means "runs disconnected on the student's phone," that's not realistic with this stack in a hackathon timeframe.

**Recommended reframing:**
- **Free tier = "self-hosted / no external API" RAG** running on your rented GPU. Text + voice. No per-query cloud cost beyond your GPU rental.
- **Premium tier = cloud vision** (image upload → Qwen2.5-VL) + Bengali TTS + faster model + higher rate limits.
- True on-device offline = future roadmap, possibly a distilled tiny model + quantized GGUF for a companion app. Don't promise it for the demo.

### 5. Your two JSONL files have inconsistent schemas — normalize before embedding
- `ICT_C1.jsonl` uses `chapter_title`; `Astrophysics_Cosmology_RAG.jsonl` uses `chapter_name`
- Astrophysics has `spec_ref`; ICT has none
- ICT `keywords` is empty `[]`; Astrophysics is populated

If you embed these as-is, your metadata filtering and citations will break across curricula.

**Action:** Adopt one unified chunk schema (provided in the CLAUDE.md). Add a `curriculum` field (`NCTB` | `Edexcel_IAL`) to EVERY chunk so retrieval can hard-filter by curriculum — an ICT student must never receive Astrophysics chunks and vice versa.

### 6. GPU cost strategy — always-on HF Spaces GPU will drain money fast
HF Spaces with persistent A10G ≈ $1.05/hr ≈ ~$750/month if always on. For a prototype/demo that's wasteful.

**Cheaper paths:**
- **HF Inference Endpoints with scale-to-zero** — spins down when idle, pay per active minute
- **RunPod / Vast.ai serverless or on-demand** — A10G/L4 around $0.30-0.50/hr, much cheaper than HF Spaces persistent
- **For the live demo:** rent the GPU only for the demo window + testing days, not the whole month

**Action:** Use scale-to-zero for everything except your live demo window.

### 7. Multiple HF Spaces (one per model) is over-engineered for a prototype
The EduCore architecture doc proposes separate Spaces for embedding, reranking, generation, and vision. That's 4 GPU instances = 4× cost and 4× ops complexity. For Shikhbo's prototype:

**Consolidate:**
- **One GPU box** running: bge-m3 + bge-reranker + your LLM (7B fits alongside embeddings on a 24GB card)
- **One vision endpoint** (Qwen2.5-VL) — only needed for premium image uploads, can be scale-to-zero
- FAISS + BM25 run on CPU alongside, cheap

---

## 🟡 SEVERITY: MEDIUM (quality and correctness)

### 8. RAG must enforce curriculum + subject + class isolation
Before semantic search, hard-filter the vector store by `curriculum`, `subject`, and `class` from the user's profile. Otherwise an A-level Astrophysics query could surface SSC ICT Bengali chunks (different language, wrong level) and vice versa.

### 9. Citations are your trust mechanism — make them mandatory
Your differentiator vs ChatGPT is "grounded in verified textbook data." Every answer must cite `chunk_id` → chapter + page. If retrieval confidence is low, the model must say "I couldn't find this in your textbook" rather than hallucinate. Bake this into the system prompt.

### 10. Hybrid search fusion needs tuning per language
RRF weighting that works for English Astrophysics won't be optimal for Bengali ICT (BM25 tokenization on Bengali is tricky — needs a Bengali-aware tokenizer, not whitespace). Validate BM25 on Bengali separately.

---

## SUMMARY — Decisions you must make today
1. Pick the premium LLM via a Bengali eval (don't default to Gemma 2B)
2. Scope Bengali OCR honestly (printed yes, handwriting experimental)
3. Move Bengali TTS to the cloud/premium tier with a real service
4. Reframe "offline" as "self-hosted no-API" not "on-device"
5. Normalize the chunk schema with a `curriculum` field
6. Use scale-to-zero GPU, rent only for demo + test windows
7. Consolidate to one GPU box + one scale-to-zero vision endpoint
