# Lean runtime image (used by staging and the single-host VPS package): API, workflow engine, document/OCR.
# It contains no model weights; Ollama runs as a separate private container when AI is enabled.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY backend/app /app/app
COPY backend/migrations /app/backend/migrations
COPY scripts/migrate_postgres.py /app/scripts/migrate_postgres.py
COPY scripts/grant_pg_runtime.py /app/scripts/grant_pg_runtime.py
COPY scripts/verify_runtime_database.py /app/scripts/verify_runtime_database.py
COPY scripts/bootstrap_postgres.py /app/scripts/bootstrap_postgres.py
RUN useradd -r -m -u 10001 workmate \
    && mkdir -p /app/data /app/data/voice /app/data/voice/audio \
    && chown -R workmate:workmate /app/data
USER workmate
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
