FROM python:3.11-slim AS translation-model-builder

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

RUN pip install --no-cache-dir \
    "ctranslate2>=4.5.0,<5.0.0" \
    "transformers[torch]>=4.45.0,<5.0.0" \
    sentencepiece

RUN pip install --no-cache-dir accelerate

RUN ct2-transformers-converter \
      --model facebook/m2m100_418M \
      --output_dir /translation/m2m100_418m \
      --quantization int8 \
      --low_cpu_mem_usage \
      --copy_files sentencepiece.bpe.model vocab.json tokenizer_config.json special_tokens_map.json

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=translation-model-builder /translation /app/models/translation

ARG PIPER_VOICE_DIR=/app/data/voice/piper
RUN mkdir -p ${PIPER_VOICE_DIR} /app/data/voice/audio /app/data/voice/whisper && \
    python -m piper.download_voices \
      --data-dir ${PIPER_VOICE_DIR} \
      en_US-lessac-medium hi_IN-pratham-medium

COPY backend/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
