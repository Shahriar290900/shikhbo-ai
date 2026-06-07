# Shikhbo — Architecture: What Lovable Builds vs What Lives on Hugging Face
## Read this before spending any Lovable credits

---

## THE SPLIT (most important concept)

Your project has TWO halves that must not be confused:

```
┌─────────────────────────────────────┐         ┌──────────────────────────────────┐
│   LOVABLE BUILDS THIS (the web app)  │         │  HUGGING FACE HOSTS THIS (the AI) │
│                                       │         │                                    │
│  • Login / Google sign-in            │         │  • bge-m3 embeddings               │
│  • Chat UI (your screenshots)        │  HTTPS  │  • FAISS + BM25 hybrid retrieval   │
│  • Subject / Mode / Quality selectors│ ──────► │  • bge-reranker                    │
│  • Database (users, chats, billing)  │  API    │  • LLM (Qwen2.5 / Gemma) generation│
│  • Stripe subscription               │ ◄────── │  • Qwen2.5-VL vision/OCR           │
│  • File upload to storage            │         │  • Returns answer + sources JSON   │
│  • Rate limiting, RLS, GDPR, admin   │         │                                    │
│  • Edge Function that calls the AI ──┼────────►│  POST /chat  { query, subject,     │
│                                       │         │     mode, curriculum }             │
└─────────────────────────────────────┘         └──────────────────────────────────┘
        React + Supabase                                  Python + Transformers
     (100 Lovable credits)                          (HF Spaces, free CPU or rented GPU)
```

**Why this split:** Lovable generates React + Supabase apps. It does not run Python ML pipelines, load 7B models, or do vector search. Trying to make it do so wastes credits and fails. The AI is a separate HTTP service.

---

## YOUR 10GB MAC CONSTRAINT — SOLVED BY THIS SPLIT

Because you cannot download models locally:
- **All model inference runs on Hugging Face Spaces**, which downloads and runs the models on HF's servers, not your Mac.
- Your Mac only runs a browser (to use Lovable + test the app). No model downloads needed.
- You deploy the HF Space by pushing code (a few KB) to HF; HF pulls the models server-side.

---

## THE HUGGING FACE AI BACKEND (deploy separately from Lovable)

This is a HF Space (Docker or Gradio) exposing an HTTP API. It is NOT built in Lovable — you build it from your existing Shikhbo Python code (you already have the RAG pipeline working per your README).

**Minimal API contract the Lovable app expects:**
```
POST https://YOUR-HF-SPACE.hf.space/chat
Request:  {
  "query": "আরপানেট নিয়ে জানতে চাই",
  "subject": "ICT",
  "curriculum": "NCTB",
  "class": "SSC",
  "mode": "normal",          // normal | simple | quiz | step_by_step
  "quality": "fast"          // fast (small model) | enhanced (bigger model)
}
Response: {
  "answer": "আরপানেট কি? ...",
  "sources": [ {"chunk_id": "SSC-ICT-C1-P1-CH1", "chapter": "...", "page": 1} ],
  "grounded": true,          // false = fell back to general explanation
  "model_used": "qwen2.5-7b"
}

POST https://YOUR-HF-SPACE.hf.space/vision   (premium only)
Request:  { "image_base64": "...", "query": "...", "subject": "..." }
Response: { "extracted_text": "...", "answer": "...", "sources": [...] }
```

**HF Space deployment for $10 / June 11-12 demo:**
- Free CPU Space: works but slow (~15-40s per answer with a 7B model) — acceptable only with a 2-3B model
- For acceptable demo speed, rent a GPU Space (T4 small ~$0.40/hr or A10G ~$1/hr) for demo hours only
- With $10: T4 small for ~12 hours of testing + demo = ~$5. Spin DOWN after each session.
- Set the Space to "sleep after inactivity" so it doesn't bill when idle

---

## HOW THE TWO CONNECT (the one Edge Function that matters)

In the Lovable app, a Supabase Edge Function named `ask-shikhbo` does this:
1. Verify the user's JWT (auth)
2. Check the user's tier + rate limit
3. Forward the query to your HF Space `/chat` endpoint (HF URL + token stored as a Supabase secret)
4. Stream/return the answer + sources back to the chat UI
5. Save the message + response to the database

This Edge Function is the ONLY bridge. Everything else in Lovable is a normal web app.

---

## CREDIT BUDGET (100 Lovable credits)

| Prompt | Plan + Build est. credits |
|---|---|
| Prompt 1: Foundation | ~18 |
| Prompt 2: Chat Engine | ~18 |
| Prompt 3: AI Integration | ~16 |
| Prompt 4: Subscription & Fortress | ~18 |
| Prompt 5: Polish & Growth | ~14 |
| Security check (free) | 0 |
| Publish | ~6 |
| **Total** | **~90** |

Leaves ~10 credits buffer for one or two fixes. Tight but workable — which is why the prompts must be precise (the skill files enforce this).
