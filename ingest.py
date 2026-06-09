"""
ingest.py — Shikhbo RAG ingestion pipeline.

Normalizes all JSONL corpora and the Astrophysics PDF to the unified chunk
schema, computes bge-m3 dense embeddings, and builds per-corpus FAISS +
BM25 indices. Outputs land in ./data/ and are read by rag.py at runtime.

Run once: python ingest.py
Re-run is idempotent (skipped if data/chunks.jsonl already exists).
"""

import json
import os
import pickle
import re
import unicodedata
from collections import Counter
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CHUNKS_FILE = DATA_DIR / "chunks.jsonl"

# ── tokenisers ────────────────────────────────────────────────────────────────

def _tokenize_bengali(text: str) -> list[str]:
    """Split Bengali text on whitespace/punctuation; keep tokens ≥ 2 chars."""
    tokens = re.findall(r"[ঀ-৿\w]+", text)
    return [t for t in tokens if len(t) >= 2]


def _tokenize_english(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _tokenize(text: str, language: str) -> list[str]:
    return _tokenize_bengali(text) if language == "bn" else _tokenize_english(text)


# ── keyword backfill for ICT (Bengali) ───────────────────────────────────────

_BN_STOPWORDS = {
    "এই", "এবং", "বা", "কিন্তু", "যে", "তার", "সে", "তা", "এটি", "এটা",
    "হয়", "হবে", "থেকে", "করে", "করা", "করতে", "করেন", "করেছে", "দিয়ে",
    "জন্য", "সাথে", "আছে", "নেই", "ছিল", "হলো", "যা", "যেন", "তবে",
    "তখন", "যখন", "এখন", "আর", "না", "হয়না", "যায়", "পারে", "কে",
    "কি", "কী", "হচ্ছে", "পর", "আমরা", "তারা", "আমি", "তুমি", "আপনি",
    "একটি", "একটা", "এক", "দুই", "তিন", "মধ্যে", "উপর", "নিচে", "তথ্য",
}

def _extract_bengali_keywords(content: str, topic: str, n: int = 15) -> list[str]:
    seed = set(_tokenize_bengali(topic)) if topic else set()
    tokens = _tokenize_bengali(content)
    tokens = [t for t in tokens if t not in _BN_STOPWORDS and not t.isdigit() and len(t) >= 3]
    freq = Counter(tokens)
    keywords = [w for w, _ in freq.most_common(n * 2) if w not in seed]
    combined = list(seed) + keywords
    seen: set[str] = set()
    result = []
    for kw in combined:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
        if len(result) == n:
            break
    return result


# ── corpus loaders ────────────────────────────────────────────────────────────

def _load_ict_chunks() -> list[dict]:
    chunks = []
    for ch in range(1, 7):
        path = Path(f"ICT_C{ch}.jsonl")
        if not path.exists():
            print(f"  [warn] {path} not found, skipping")
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec["curriculum"] = "NCTB"
                rec["language"] = "bn"
                rec.setdefault("spec_ref", None)
                rec.setdefault("prerequisite", None)
                # backfill empty keywords
                if not rec.get("keywords"):
                    rec["keywords"] = _extract_bengali_keywords(
                        rec.get("content", ""), rec.get("topic", "")
                    )
                rec["embedding_vector"] = None
                chunks.append(rec)
    print(f"  Loaded {len(chunks)} ICT chunks")
    return chunks


def _load_astrophysics_chunks() -> list[dict]:
    path = Path("Astrophysics_Cosmology_RAG.jsonl")
    if not path.exists():
        print(f"  [warn] {path} not found, skipping")
        return []
    chunks = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # rename chapter_name → chapter_title
            if "chapter_name" in rec and "chapter_title" not in rec:
                rec["chapter_title"] = rec.pop("chapter_name")
            rec["curriculum"] = "Edexcel_IAL"
            rec["language"] = "en"
            rec.setdefault("spec_ref", None)
            rec.setdefault("prerequisite", None)
            rec.setdefault("keywords", [])
            rec["embedding_vector"] = None
            chunks.append(rec)
    print(f"  Loaded {len(chunks)} Astrophysics JSONL chunks")
    return chunks


def _chunk_text(text: str, chunk_size: int = 1600, overlap: int = 200) -> list[str]:
    """Split text into overlapping character-based chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def _load_pdf_chunks() -> list[dict]:
    path = Path("Astrophysics_Cosmology_Notes.pdf")
    if not path.exists():
        print(f"  [warn] {path} not found, skipping")
        return []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("  [warn] PyMuPDF not installed — skipping PDF chunking")
        return []

    chunks = []
    doc = fitz.open(str(path))
    for page_idx in range(len(doc)):
        page_no = page_idx + 1
        text = doc[page_idx].get_text().strip()
        if not text:
            continue
        # normalise whitespace
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        sub_chunks = _chunk_text(text, chunk_size=1600, overlap=200)
        for chunk_idx, sub in enumerate(sub_chunks, start=1):
            sub = sub.strip()
            if len(sub) < 80:
                continue
            chunk_id = f"EDEXCEL-IAL-PHYS-NOTES-P{page_no}-CH{chunk_idx}"
            chunks.append({
                "chunk_id": chunk_id,
                "curriculum": "Edexcel_IAL",
                "class": "A-level",
                "subject": "Physics",
                "language": "en",
                "chapter_no": "5.6-NOTES",
                "chapter_title": "Astrophysics & Cosmology Notes",
                "page_no": page_no,
                "topic": "",
                "spec_ref": None,
                "prerequisite": None,
                "keywords": [],
                "token_count": len(sub) // 4,
                "content": sub,
                "embedding_vector": None,
            })
    doc.close()
    print(f"  Loaded {len(chunks)} PDF chunks from {path.name}")
    return chunks


# ── corpus key ────────────────────────────────────────────────────────────────

def corpus_key(chunk: dict) -> str:
    c = chunk["curriculum"].replace(" ", "_")
    s = chunk["subject"].replace(" ", "_")
    cl = chunk["class"].replace(" ", "_").replace("-", "_")
    return f"{c}__{s}__{cl}"


# ── embedding ─────────────────────────────────────────────────────────────────

def compute_embeddings(model: SentenceTransformer, texts: list[str], batch_size: int = 32) -> np.ndarray:
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.array(vecs, dtype=np.float32)


# ── main ──────────────────────────────────────────────────────────────────────

def run_ingest(force: bool = False) -> None:
    if CHUNKS_FILE.exists() and not force:
        # check that at least one FAISS index also exists
        existing = list(DATA_DIR.glob("faiss_*.index"))
        if existing:
            print("Ingest already complete (data/ indices exist). Skipping.")
            return

    print("=== Shikhbo ingest starting ===")

    # ── 1. load all corpora ──
    print("Loading corpora…")
    all_chunks: list[dict] = []
    all_chunks.extend(_load_ict_chunks())
    all_chunks.extend(_load_astrophysics_chunks())
    all_chunks.extend(_load_pdf_chunks())
    print(f"  Total chunks: {len(all_chunks)}")

    if not all_chunks:
        raise RuntimeError("No chunks loaded — check that JSONL/PDF files are present.")

    # ── 2. save normalised chunks (without embedding vectors) ──
    print(f"Saving normalised chunks → {CHUNKS_FILE}")
    with open(CHUNKS_FILE, "w", encoding="utf-8") as fh:
        for c in all_chunks:
            out = {k: v for k, v in c.items() if k != "embedding_vector"}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")

    # ── 3. group by corpus key ──
    by_key: dict[str, list[tuple[int, dict]]] = {}
    for idx, chunk in enumerate(all_chunks):
        key = corpus_key(chunk)
        by_key.setdefault(key, []).append((idx, chunk))
    print(f"  Corpus keys: {list(by_key.keys())}")

    # ── 4. load embedding model ──
    print("Loading BAAI/bge-m3…")
    model = SentenceTransformer("BAAI/bge-m3", device="cpu", model_kwargs={"use_safetensors": True})

    # ── 5. per-corpus FAISS + BM25 ──
    for key, idx_chunk_pairs in by_key.items():
        print(f"\nProcessing corpus '{key}' ({len(idx_chunk_pairs)} chunks)…")
        chunks = [c for _, c in idx_chunk_pairs]
        lang = chunks[0]["language"]

        # embeddings
        print("  Computing embeddings…")
        texts = [c["content"] for c in chunks]
        vecs = compute_embeddings(model, texts)

        # FAISS
        dim = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vecs)
        faiss_path = DATA_DIR / f"faiss_{key}.index"
        faiss.write_index(index, str(faiss_path))
        print(f"  FAISS index saved → {faiss_path} ({index.ntotal} vectors)")

        # index_map: ordered list of chunk_ids matching FAISS rows
        index_map = [c["chunk_id"] for c in chunks]
        map_path = DATA_DIR / f"index_map_{key}.json"
        with open(map_path, "w", encoding="utf-8") as fh:
            json.dump(index_map, fh, ensure_ascii=False)
        print(f"  Index map saved → {map_path}")

        # BM25
        tokenized = [_tokenize(c["content"], lang) for c in chunks]
        bm25 = BM25Okapi(tokenized)
        bm25_path = DATA_DIR / f"bm25_{key}.pkl"
        with open(bm25_path, "wb") as fh:
            pickle.dump(bm25, fh)
        docs_path = DATA_DIR / f"bm25_docs_{key}.json"
        with open(docs_path, "w", encoding="utf-8") as fh:
            json.dump(index_map, fh, ensure_ascii=False)
        print(f"  BM25 index saved → {bm25_path}")

    print("\n=== Ingest complete ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-ingest even if indices exist")
    args = parser.parse_args()
    run_ingest(force=args.force)
