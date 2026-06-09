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
ENV HF_XET_HIGH_PERFORMANCE=1
ENV HF_HUB_DOWNLOAD_TIMEOUT=600

# install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/.cache && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/startup.sh
USER appuser

EXPOSE 7860

CMD ["bash", "/app/startup.sh"]
