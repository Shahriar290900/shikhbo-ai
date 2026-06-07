FROM python:3.11-slim

# system deps for PyMuPDF (libGL) and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install Python deps first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy source and data files
COPY . .

# HF Spaces requires a writable data dir and port 7860
RUN mkdir -p data

# HF Spaces runs containers as user 1000 by default
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

# ingest.py is called lazily from app.py lifespan (skipped if indices exist)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
