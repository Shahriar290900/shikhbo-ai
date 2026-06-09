FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV HF_HOME=/app/.cache
ENV HF_HUB_CACHE=/app/.cache/huggingface
ENV HF_HUB_ENABLE_HF_TRANSFER=1
ENV HF_HUB_DOWNLOAD_TIMEOUT=120

# install deps first — cached separately from model downloads
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# download models at build time, each in its own layer so Docker can cache
# them independently — changing app code will NOT re-trigger these layers
RUN huggingface-cli download BAAI/bge-m3 --quiet
RUN huggingface-cli download BAAI/bge-reranker-v2-m3 --quiet
RUN huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct --quiet

# copy app code last — model layers above stay cached on every code change
COPY . .

RUN mkdir -p /app/data /app/.cache && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
