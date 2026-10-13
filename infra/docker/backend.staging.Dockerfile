# Lean staging runtime: tests PostgreSQL, auth, document/OCR and UI integration
# without downloading large translation, TTS or Ollama model weights.
# Do not use for a voice performance acceptance test.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY backend/app /app/app
COPY backend/migrations /app/backend/migrations
COPY scripts/migrate_postgres.py /app/scripts/migrate_postgres.py
COPY scripts/grant_pg_runtime.py /app/scripts/grant_pg_runtime.py
COPY scripts/verify_runtime_database.py /app/scripts/verify_runtime_database.py
RUN useradd -r -m -u 10001 workmate \
    && mkdir -p /app/data /app/data/voice /app/data/voice/audio \
    && chown -R workmate:workmate /app/data
USER workmate
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
