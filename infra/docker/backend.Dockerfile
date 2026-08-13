FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG PIPER_VOICE_DIR=/app/data/voice/piper
RUN mkdir -p ${PIPER_VOICE_DIR} /app/data/voice/audio /app/data/voice/whisper && \
    python -m piper.download_voices \
      --data-dir ${PIPER_VOICE_DIR} \
      en_US-lessac-medium hi_IN-pratham-medium

COPY backend/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
