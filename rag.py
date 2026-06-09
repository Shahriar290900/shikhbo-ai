"""
rag.py — Shikhbo hybrid retrieval engine.

Loads the pre-built FAISS + BM25 indices produced by ingest.py and exposes
ShikhboRAG.retrieve() for use by app.py.

Retrieval pipeline per query:
  hard-filter by corpus key → dense (bge-m3) + sparse (BM25) →
  Reciprocal Rank Fusion → rerank (bge-reranker-v2-m3) → confidence gate
"""

import json
import os
import pickle
import re
import threading
import time
from pathlib import Path

import faiss
import numpy as np
from FlagEmbedding import BGEM3FlagModel, FlagReranker


def _load_with_retry(name: str, loader, retries: int = 3, delay: float = 10.0):
    for attempt in range(1, retries + 1):
        try:
            print(f"Loading {name}… (attempt {attempt}/{retries})")
            obj = loader()
            print(f"{name} ready.")
            return obj
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(f"Failed to load {name} after {retries} attempts") from exc
            print(f"[warn] {name} attempt {attempt} failed: {exc}. Retrying in {delay}s…")
            time.sleep(delay)

DATA_DIR = Path("data")

# ── tokenisers (mirrors ingest.py) ───────────────────────────────────────────

def _tokenize_bengali(text: str) -> list[str]:
    tokens = re.findall(r"[ঀ-৿\w]+", text)
    return [t for t in tokens if len(t) >= 2]


def _tokenize_english(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _tokenize(text: str, language: str) -> list[str]:
    return _tokenize_bengali(text) if language == "bn" else _tokenize_english(text)


# ── corpus key helper ─────────────────────────────────────────────────────────

def _corpus_key(curriculum: str, subject: str, class_: str) -> str:
    def _norm(s: str) -> str:
        return s.replace(" ", "_").replace("-", "_")
    return f"{_norm(curriculum)}__{_norm(subject)}__{_norm(class_)}"


# ── RRF ───────────────────────────────────────────────────────────────────────

def _rrf(
    dense_ids: list[str],
    sparse_ids: list[str],
    w_dense: float,
    w_sparse: float,
    k: int = 60,
) -> list[str]:
    """
    Reciprocal Rank Fusion over two ranked lists.
    Returns merged list of chunk_ids sorted by fused score descending.
    """
    scores: dict[str, float] = {}
    for rank, cid in enumerate(dense_ids):
        scores[cid] = scores.get(cid, 0.0) + w_dense / (k + rank + 1)
    for rank, cid in enumerate(sparse_ids):
        scores[cid] = scores.get(cid, 0.0) + w_sparse / (k + rank + 1)
    return sorted(scores, key=lambda cid: scores[cid], reverse=True)


# ── main class ────────────────────────────────────────────────────────────────

class ShikhboRAG:
    # Supported (curriculum, subject, class) triples
    KNOWN_CORPORA = {
        ("NCTB", "ICT", "SSC"),
        ("Edexcel_IAL", "Physics", "A-level"),
    }

    def __init__(self) -> None:
        self._load_chunks()
        self._load_indices()
        _use_fp16 = os.getenv("LLM_DEVICE", "cpu") != "cpu"
        self._embed_model = _load_with_retry(
            "BAAI/bge-m3",
            lambda: BGEM3FlagModel("BAAI/bge-m3", use_fp16=_use_fp16),
        )
        self._reranker_obj: object | None = None
        self._reranker_lock = threading.Lock()
        print("ShikhboRAG ready.")

    def _get_reranker(self) -> FlagReranker:
        if self._reranker_obj is None:
            with self._reranker_lock:
                if self._reranker_obj is None:
                    _use_fp16 = os.getenv("LLM_DEVICE", "cpu") != "cpu"
                    self._reranker_obj = _load_with_retry(
                        "BAAI/bge-reranker-v2-m3",
                        lambda: FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=_use_fp16),
                    )
        return self._reranker_obj

    # ── loading helpers ───────────────────────────────────────────────────────

    def _load_chunks(self) -> None:
        path = DATA_DIR / "chunks.jsonl"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found — run ingest.py first"
            )
        self._chunks: dict[str, dict] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    c = json.loads(line)
                    self._chunks[c["chunk_id"]] = c
        print(f"  Loaded {len(self._chunks)} chunks from {path}")

    def _load_indices(self) -> None:
        self._faiss: dict[str, faiss.Index] = {}
        self._index_maps: dict[str, list[str]] = {}
        self._bm25: dict[str, object] = {}
        self._bm25_docs: dict[str, list[str]] = {}
        self._corpus_lang: dict[str, str] = {}

        for key_tuple in self.KNOWN_CORPORA:
            key = _corpus_key(*key_tuple)
            faiss_path = DATA_DIR / f"faiss_{key}.index"
            map_path = DATA_DIR / f"index_map_{key}.json"
            bm25_path = DATA_DIR / f"bm25_{key}.pkl"
            docs_path = DATA_DIR / f"bm25_docs_{key}.json"

            if not faiss_path.exists():
                print(f"  [warn] {faiss_path} missing — corpus '{key}' unavailable")
                continue

            self._faiss[key] = faiss.read_index(str(faiss_path))
            with open(map_path, encoding="utf-8") as fh:
                self._index_maps[key] = json.load(fh)
            with open(bm25_path, "rb") as fh:
                self._bm25[key] = pickle.load(fh)
            with open(docs_path, encoding="utf-8") as fh:
                self._bm25_docs[key] = json.load(fh)

            # infer language from first chunk in this corpus
            first_id = self._index_maps[key][0]
            self._corpus_lang[key] = self._chunks.get(first_id, {}).get("language", "en")
            print(f"  Loaded index for '{key}' ({self._faiss[key].ntotal} vectors, lang={self._corpus_lang[key]})")

    # ── public API ────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        curriculum: str,
        subject: str,
        class_: str,
        top_k: int = 5,
    ) -> tuple[list[dict], bool]:
        """
        Returns (chunks, grounded).
        chunks — list of chunk dicts from the corpus.
        grounded — False if max reranker score < CONFIDENCE_THRESHOLD.
        """
        key = _corpus_key(curriculum, subject, class_)
        if key not in self._faiss:
            raise ValueError(
                f"Unknown corpus key '{key}'. "
                f"Known: {list(self._faiss.keys())}"
            )

        threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.3"))
        lang = self._corpus_lang[key]

        # language-tuned RRF weights
        w_dense, w_sparse = (0.6, 0.4) if lang == "en" else (0.4, 0.6)

        # ── dense search ──
        query_vec = self._embed_query(query)
        dense_ids = self._dense_search(key, query_vec, top_n=30)

        # ── sparse search ──
        sparse_ids = self._sparse_search(key, query, lang, top_n=30)

        # ── RRF ──
        fused = _rrf(dense_ids, sparse_ids, w_dense=w_dense, w_sparse=w_sparse)
        candidates = fused[:20]

        if not candidates:
            return [], False

        # ── rerank ──
        pairs = [(query, self._chunks[cid]["content"]) for cid in candidates if cid in self._chunks]
        if not pairs:
            return [], False

        scores = self._get_reranker().compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]

        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

        max_score = ranked[0][1] if ranked else 0.0
        if max_score < threshold:
            return [], False

        result_chunks = [
            self._chunks[cid]
            for cid, _ in ranked[:top_k]
            if cid in self._chunks
        ]
        return result_chunks, True

    def format_sources(self, chunks: list[dict]) -> list[dict]:
        return [
            {
                "chunk_id": c["chunk_id"],
                "chapter": c.get("chapter_title", ""),
                "chapter_no": c.get("chapter_no", ""),
                "page": c.get("page_no", 0),
            }
            for c in chunks
        ]

    # ── internals ─────────────────────────────────────────────────────────────

    def _embed_query(self, query: str) -> np.ndarray:
        out = self._embed_model.encode([query], batch_size=1, max_length=512)
        vec = np.array(out["dense_vecs"][0], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.reshape(1, -1)

    def _dense_search(self, key: str, query_vec: np.ndarray, top_n: int) -> list[str]:
        index = self._faiss[key]
        index_map = self._index_maps[key]
        k = min(top_n, index.ntotal)
        _, I = index.search(query_vec, k)
        return [index_map[i] for i in I[0] if 0 <= i < len(index_map)]

    def _sparse_search(self, key: str, query: str, lang: str, top_n: int) -> list[str]:
        bm25 = self._bm25[key]
        docs = self._bm25_docs[key]
        tokens = _tokenize(query, lang)
        if not tokens:
            return []
        scores = bm25.get_scores(tokens)
        ranked_idx = np.argsort(scores)[::-1][:top_n]
        return [docs[i] for i in ranked_idx if scores[i] > 0]
