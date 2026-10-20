"""Unicode voice metric arithmetic and isolation gates; no real ASR accuracy claims."""
import json
from pathlib import Path

import pytest

from evals.voice_quality import command_terms, edit_counts, evaluate, graphemes, run_manifest

FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "voice_metric_sanity.json"


def test_insertions_deletions_and_substitutions():
    assert edit_counts(["a", "b"], ["a", "c"]) == {"distance": 1, "sub": 1, "del": 0, "ins": 0}
    assert edit_counts(["a", "b"], ["a"]) == {"distance": 1, "sub": 0, "del": 1, "ins": 0}
    assert edit_counts(["a"], ["a", "b"]) == {"distance": 1, "sub": 0, "del": 0, "ins": 1}
    assert edit_counts([], ["a"])["ins"] == 1


def test_hindi_vowel_mark_is_one_grapheme_with_base():
    assert "ै" in graphemes("पैकेज")[0]
    assert len(graphemes("पै")) == 1


def test_language_stratified_report_is_not_production_accuracy():
    report = run_manifest(FIXTURE)
    assert report["provenance"] == "labeled_text_metric_sanity_only"
    assert report["overall"]["samples"] == 10
    assert set(report["by_language"]) == {"en", "hi", "hinglish"}
    assert report["overall"]["wer"] > 0
    assert report["by_language"]["en"]["language_detection_accuracy"] == 1
    assert report["by_language"]["hinglish"]["language_detection_accuracy"] is None
    exported = json.dumps(report, ensure_ascii=False)
    for private_text in ("Inspect the security seal", "पैकेज क्षतिग्रस्त है", "Pallet का barcode"):
        assert private_text not in exported
    assert "accuracy score" in report["metric_notes"]


def test_command_confusion_is_surfaced_even_when_wer_is_low():
    report = evaluate([
        {"id": "x", "language": "en", "reference": "done now", "hypothesis": "do now"},
        {"id": "y", "language": "en", "reference": "inspect bin", "hypothesis": "pause bin"},
    ], provenance="unit")
    assert report["overall"]["missed_command_cases"] == 1
    assert report["overall"]["false_command_cases"] == 1


def test_bad_manifest_and_duplicate_id_rejected(tmp_path):
    with pytest.raises(ValueError, match="unique id"):
        evaluate([
            {"id": "a", "language": "en", "reference": "a", "hypothesis": "b"},
            {"id": "a", "language": "en", "reference": "a", "hypothesis": "b"},
        ], provenance="unit")
    with pytest.raises(ValueError, match="en/hi/hinglish"):
        evaluate([{"id": "x", "language": "fr", "reference": "oui", "hypothesis": ""}], provenance="unit")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([{"id":"x","language":"en","reference":"hello","audio":"clip.wav","hypothesis":"hello"}]))
    with pytest.raises(ValueError, match="requires --transcribe"):
        run_manifest(path)


def test_real_audio_paths_cannot_escape_manifest_directory(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([{"id":"x","language":"en","reference":"hello","audio":"../out.wav"}]))
    from app.services.speech_recognition_service import FasterWhisperSpeechRecognitionService
    monkeypatch.setattr(FasterWhisperSpeechRecognitionService, "_transcribe_sync",
                        lambda *_a: (_ for _ in ()).throw(AssertionError("invalid path got to STT")))
    with pytest.raises(ValueError, match="outside"):
        run_manifest(path, transcribe=True)


def test_live_transcription_benchmark_uses_actual_STT_not_saved_prediction(tmp_path, monkeypatch):
    from app.models.voice import TranscriptionResult
    from app.services.speech_recognition_service import FasterWhisperSpeechRecognitionService
    (tmp_path / "clip.wav").write_bytes(b"not real audio; the decoder is mocked")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([
        {"id":"x", "language":"en", "reference":"inspect seal",
         "audio":"clip.wav", "hypothesis":"dangerously stale"}
    ]))
    monkeypatch.setattr(FasterWhisperSpeechRecognitionService, "_transcribe_sync",
                        lambda *_a: TranscriptionResult(transcript="inspect seal", language="en", confidence=0.91))
    report = run_manifest(path, transcribe=True)
    assert report["provenance"] == "held_out_audio"
    assert report["overall"]["wer"] == 0
    assert report["overall"]["latency_p95_ms"] is not None
