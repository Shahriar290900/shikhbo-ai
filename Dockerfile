# PyTorch base image ships CUDA-enabled torch so the T4 GPU is used out of the box.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# Run as non-root (HuggingFace best practice; uid must be 1000).
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# --- CRITICAL: redirect HF caches off the 50 GB non-persistent root disk ---
# Using /tmp so the model re-downloads on every cold start but never fills root.
# If you attach persistent HF storage, change /tmp -> /data and it downloads once.
ENV HF_HOME=/tmp/hf_cache \
    HF_HUB_CACHE=/tmp/hf_cache/hub \
    TRANSFORMERS_CACHE=/tmp/hf_cache/transformers \
    TORCH_HOME=/tmp/hf_cache/torch \
    HF_HUB_DOWNLOAD_TIMEOUT=600
RUN mkdir -p /tmp/hf_cache/hub /tmp/hf_cache/transformers /tmp/hf_cache/torch

WORKDIR /app
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY --chown=user . /app

# HF routes public traffic to app_port (7860). Uvicorn MUST bind 0.0.0.0:7860.
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
