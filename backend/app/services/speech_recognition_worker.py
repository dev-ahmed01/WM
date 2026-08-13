"""Short-lived Faster-Whisper worker for memory-constrained deployments."""

import logging
from pathlib import Path
import sys

from app.services.speech_recognition_service import (
    FasterWhisperSpeechRecognitionService,
    SpeechRecognitionError,
)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    audio_path = Path(sys.argv[1]).resolve()
    requested_language = None if sys.argv[2] == "auto" else sys.argv[2]
    try:
        result = FasterWhisperSpeechRecognitionService()._transcribe_sync(
            audio_path, requested_language
        )
    except SpeechRecognitionError:
        logging.getLogger("workmate.voice.stt.worker").exception("Transcription failed")
        return 1
    sys.stdout.write(result.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
