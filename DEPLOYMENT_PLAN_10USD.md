# Shikhbo — $10 Demo Deployment Plan
## Demo dates: June 11–12, 2026 · Total budget: $10

---

## THE KEY INSIGHT: Run almost everything on your Mac. Spend ~$0.

Your Mac (Apple Silicon) can run the entire text + voice + RAG stack locally via Ollama. You do NOT need to rent GPU for the core experience. The $10 is a safety buffer, mostly for the vision/OCR premium feature during the demo only.

---

## WHAT RUNS WHERE

| Component | Where | Cost |
|---|---|---|
| LLM (Gemma-2-9B or Qwen2.5-7B, quantized) | Mac via Ollama | $0 |
| Embeddings (bge-m3) | Mac (CPU/MPS) | $0 |
| Reranker (bge-reranker-v2-m3) | Mac (CPU/MPS) | $0 |
| FAISS vector store | Mac (local file) | $0 |
| BM25 sparse search | Mac (in-memory) | $0 |
| STT (Faster-Whisper) | Mac (local) | $0 |
| English TTS (Piper) | Mac (local) | $0 |
| Flask backend + MySQL | Mac (localhost) | $0 |
| **Vision/OCR (premium image upload)** | **Rented GPU OR small local model** | **≤ $6** |

---

## MAC FEASIBILITY CHECK (do this first)

Run in terminal:
```bash
# Check your RAM
sysctl hw.memsize | awk '{print $2/1073741824 " GB"}'
```

- **16GB+ Mac:** Can run Gemma-2-9B-Q4 (~6GB) OR Qwen2.5-7B-Q4 (~5GB) comfortably alongside embeddings. ✅ Run everything local.
- **8GB Mac:** Use Gemma-2-2B + Qwen2.5-3B only. Bigger models will swap and be slow. Consider renting GPU for the demo LLM.

Quantized models via Ollama are already Q4 by default — they fit far smaller than full precision.

---

## THE VISION/OCR DECISION (your only real cost)

Premium image upload needs a vision model. Three options ranked by cost:

### Option A — Small vision model on Mac ($0) ✅ RECOMMENDED
```bash
ollama pull qwen2.5vl:3b      # ~3GB, runs on Mac, decent for English + diagrams
```
Good enough for an Astrophysics diagram or English homework photo. Bengali OCR will be weak — acceptable for a demo if you show English image upload.

### Option B — Rent GPU for vision, demo hours only (~$5)
- RunPod/Vast.ai, an L4 or A10G at ~$0.40/hr
- Spin up 1 hour before demo, run Qwen2.5-VL-7B, spin down after
- 2 demo days × 3 hours + 2 hours testing = 8 hours ≈ $3.20–$4
- **Set a billing alert at $8** so you never overrun

### Option C — Free HF Inference API for vision
- Some VLMs are available on HF serverless inference free tier (rate-limited)
- Unreliable for a live demo — use only as backup

**Recommendation:** Option A for safety (demo never depends on network/billing), with Option B ready if you want the stronger 7B vision quality for the judges.

---

## DEMO-DAY RUNBOOK (June 11 & 12)

**The night before:**
1. `ollama pull` all models (do this on good wifi — multi-GB downloads)
2. Build the FAISS index from your normalized chunks (one-time, local)
3. Full dry run: text query, voice query, image upload — end to end
4. Confirm citations render correctly

**1 hour before demo:**
1. Start Ollama, Flask, MySQL locally
2. If using rented GPU vision (Option B): spin up the pod, test one image, leave running
3. Pre-warm the models (send one dummy query so first real query isn't slow)

**During demo:**
- Lead with the text RAG + citation (your strongest, most reliable feature)
- Show voice input (Bengali STT)
- Show one image upload (English/diagram — your safe OCR case)
- Show the three learning modes (Simple / Quiz / Step-by-Step)

**After demo:**
- If rented GPU: SPIN IT DOWN immediately (this is where money leaks)

---

## REALISTIC BUDGET BREAKDOWN

| Item | Cost |
|---|---|
| All local Mac inference (LLM, RAG, voice, embeddings) | $0.00 |
| Vision GPU rental — Option A (local 3B) | $0.00 |
| Vision GPU rental — Option B (8 hrs @ $0.40) | $3.20 |
| Buffer for overruns / re-tests | $4.00 |
| **Total** | **$3–7 of your $10** |

You finish with money to spare. The $10 budget is comfortable IF you run the core stack locally and only rent for vision during demo hours.

---

## DON'T DO THESE (money/time wasters)
- ❌ Don't rent always-on HF Spaces GPU (~$750/mo) — you'd burn $10 in 10 hours
- ❌ Don't run 4 separate model Spaces — co-locate on the Mac
- ❌ Don't deploy to cloud "to be safe" — local is more reliable for a live demo (no network dependency)
- ❌ Don't forget to spin DOWN any rented GPU after each demo session
