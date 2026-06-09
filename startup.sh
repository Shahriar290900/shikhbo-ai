#!/bin/bash
# startup.sh — resolve HF cache directory before starting uvicorn.
#
# HF_HOME can be overridden by a Space variable (e.g. /data/hf_cache for
# persistent storage). If that path is not writable — because persistent
# storage is not enabled — fall back to /app/.cache which is always
# writable (chowned to appuser in the Dockerfile).

REQUESTED="${HF_HOME:-/app/.cache}"

if mkdir -p "$REQUESTED" 2>/dev/null && [ -w "$REQUESTED" ]; then
    echo "[startup] HF cache: $REQUESTED"
    export HF_HOME="$REQUESTED"
    export HF_HUB_CACHE="$REQUESTED/huggingface"
    mkdir -p "$REQUESTED/huggingface"
else
    echo "[startup] WARNING: $REQUESTED is not writable — falling back to /app/.cache"
    export HF_HOME=/app/.cache
    export HF_HUB_CACHE=/app/.cache/huggingface
    mkdir -p /app/.cache/huggingface
fi

exec uvicorn app:app --host 0.0.0.0 --port 7860
