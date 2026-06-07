# Shikhbo AI Backend — HF Spaces Deployment

FastAPI RAG backend for Shikhbo. Runs on a Hugging Face Space (Docker).  
Exposes `POST /chat` and `POST /vision` consumed by the Lovable frontend.

---

## Prerequisites

- Hugging Face account with Spaces access
- `git` + `git-lfs` installed locally
- The data files (`ICT_C*.jsonl`, `Astrophysics_Cosmology_RAG.jsonl`, `Astrophysics_Cosmology_Notes.pdf`) in the repo root

---

## 1. Create the HF Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
2. **SDK:** Docker
3. **Visibility:** Private (keeps your API token safe)
4. Clone the empty Space repo:
   ```bash
   git clone https://huggingface.co/spaces/YOUR_USERNAME/shikhbo-backend
   cd shikhbo-backend
   ```

---

## 2. Track large files with Git LFS

```bash
git lfs install
git lfs track "*.jsonl" "*.pdf"
git add .gitattributes
```

---

## 3. Push the code

Copy all project files into the cloned Space directory, then:

```bash
git add .
git commit -m "initial shikhbo backend"
git push
```

The Space will build automatically. Watch logs at  
`https://huggingface.co/spaces/YOUR_USERNAME/shikhbo-backend` → **Logs** tab.

First build downloads bge-m3 (~570 MB), bge-reranker (~570 MB), and the LLM
(~3 GB for 1.5B model). Allow ~10–15 minutes.

---

## 4. Set Space secrets (env vars)

Go to your Space → **Settings** → **Repository secrets**:

| Secret | Value | Notes |
|---|---|---|
| `API_TOKEN` | A random secret string | Shared with your Supabase Edge Function |
| `LLM_MODEL` | `Qwen/Qwen2.5-1.5B-Instruct` | CPU default; swap to 7B for GPU demo |
| `LLM_DEVICE` | `cpu` | Change to `cuda` on a GPU Space |
| `MAX_NEW_TOKENS` | `512` | Increase on GPU if needed |
| `CONFIDENCE_THRESHOLD` | `0.3` | Lower = more results; higher = stricter grounding |
| `VISION_ENABLED` | `false` | Set `true` only on a GPU Space |

---

## 5. Test the Space (CPU free tier)

```bash
export HF_URL="https://YOUR_USERNAME-shikhbo-backend.hf.space"
export TOKEN="your-api-token"

# health check
curl $HF_URL/health

# Bengali ICT query
curl -s -X POST $HF_URL/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "আরপানেট কি?",
    "curriculum": "NCTB",
    "class": "SSC",
    "subject": "ICT",
    "mode": "normal",
    "quality": "fast"
  }' | python3 -m json.tool

# English Astrophysics query
curl -s -X POST $HF_URL/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain Newton law of universal gravitation",
    "curriculum": "Edexcel_IAL",
    "class": "A-level",
    "subject": "Physics",
    "mode": "step_by_step",
    "quality": "fast"
  }' | python3 -m json.tool

# confidence gate test (gibberish → grounded: false)
curl -s -X POST $HF_URL/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "xkqzjwplm banana",
    "curriculum": "NCTB",
    "class": "SSC",
    "subject": "ICT",
    "mode": "normal",
    "quality": "fast"
  }' | python3 -m json.tool

# vision endpoint on CPU → expect 503
curl -s -X POST $HF_URL/vision \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"AA==","query":"test","subject":"ICT","curriculum":"NCTB","class":"SSC"}'
```

Expected for vision on CPU: `{"detail":"Vision requires GPU tier…"}`

---

## 6. Demo day — upgrade to GPU

For the June 11–12 demo, upgrade to a T4 Small GPU Space (~$0.40/hr):

1. Go to Space → **Settings** → **Space hardware** → **T4 Small**
2. Update secrets:
   - `LLM_MODEL` → `Qwen/Qwen2.5-7B-Instruct`
   - `LLM_DEVICE` → `cuda`
   - `VISION_ENABLED` → `true`
3. Restart the Space 1 hour before demo to let it warm up

**After the demo — spin it back down to CPU to stop billing:**
1. Space → Settings → Space hardware → **CPU Basic (free)**

Set a billing alert at **$8** at [huggingface.co/settings/billing](https://huggingface.co/settings/billing).

---

## 7. Ingest behaviour

`ingest.py` is called from `app.py`'s startup and is **idempotent** — it skips
if `data/faiss_*.index` files already exist. To force a full re-ingest:

```bash
# SSH into the Space (if enabled) or add to CMD temporarily:
python ingest.py --force
```

Or simply delete the `data/` directory contents and restart the Space.

---

## Architecture summary

```
Lovable frontend (React + Supabase)
         |
   Supabase Edge Function "ask-shikhbo"
         | Authorization: Bearer $API_TOKEN
         v
POST /chat  (this Space)
  ├─ ShikhboRAG.retrieve()
  │    ├─ FAISS dense  (bge-m3, per-corpus index)
  │    ├─ BM25 sparse  (language-aware tokeniser)
  │    ├─ RRF fusion
  │    └─ bge-reranker-v2-m3 → confidence gate
  └─ LLM generation (Qwen2.5-1.5B/7B)
       └─ answer + sources + grounded flag
```

Curriculum isolation is enforced by **separate FAISS + BM25 indices** per
`curriculum__subject__class` key — NCTB/ICT and Edexcel/Physics chunks never
share an index and cannot bleed into each other.
