"""Privacy-first held-out speech benchmark; no bundled audio or claimed field accuracy.

Usage:
  PYTHONPATH=backend python backend/evals/voice_quality.py --manifest /path/to/gold.json --transcribe
  PYTHONPATH=backend python backend/evals/voice_quality.py --manifest backend/evals/fixtures/voice_metric_sanity.json

The bundled fixture contains TEXT ONLY, designed to validate metric arithmetic.
Real WER/CER can be measured ONLY by --transcribe on independently annotated
private audio files. The report never saves transcripts, references, or audio.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import unicodedata
from pathlib import Path
from typing import Any

LANGUAGES = {"en", "hi", "hinglish"}
COMMAND_WORDS = {
    "done", "complete", "completed", "finish", "finished", "next", "skip",
    "pause", "resume", "stop", "cancel", "abandon", "yes", "confirm",
    "पूरा", "समाप्त", "अगला", "रुको", "बंद", "हाँ",
}


def normalized_words(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value).casefold()
    return ["".join(ch for ch in raw if not unicodedata.category(ch).startswith("P"))
            for raw in text.split() if any(ch.isalnum() for ch in raw)]


def graphemes(value: str) -> list[str]:
    """Approximate Unicode user-perceived characters (base plus Indic marks)."""
    text = " ".join(normalized_words(value))
    parts: list[str] = []
    for char in text:
        cat = unicodedata.category(char)
        if cat in {"Mn", "Mc", "Me"} and parts:
            parts[-1] += char
        else:
            parts.append(char)
    return parts


def edit_counts(reference: list[str], candidate: list[str]) -> dict[str, int]:
    """Levenshtein with explicit S/D/I counts; deterministic tie handling."""
    old = [(i, 0, 0, i) for i in range(len(candidate) + 1)]
    for ref in reference:
        new = [(old[0][0] + 1, old[0][1], old[0][2] + 1, old[0][3])]
        for j, hyp in enumerate(candidate, 1):
            match = old[j - 1] if ref == hyp else (
                old[j - 1][0] + 1, old[j - 1][1] + 1,
                old[j - 1][2], old[j - 1][3]
            )
            delete = (old[j][0] + 1, old[j][1], old[j][2] + 1, old[j][3])
            insert = (new[j - 1][0] + 1, new[j - 1][1], new[j - 1][2], new[j - 1][3] + 1)
            new.append(min(match, delete, insert, key=lambda item: (item[0], item[1], item[2], item[3])))
        old = new
    distance, sub, deletion, insertion = old[-1]
    return {"distance": distance, "sub": sub, "del": deletion, "ins": insertion}


def command_terms(text: str) -> set[str]:
    return set(normalized_words(text)).intersection(COMMAND_WORDS)


def evaluate(items: list[dict[str, Any]], *, provenance: str) -> dict[str, Any]:
    if not items:
        raise ValueError("No annotated examples supplied")
    ids: set[str] = set()
    groups: dict[str, dict[str, Any]] = {}
    for row in items:
        key = str(row.get("id", ""))
        language = row.get("language")
        if not key or key in ids or language not in LANGUAGES:
            raise ValueError("Every item requires a unique id and en/hi/hinglish language")
        ids.add(key)
        truth, hypothesis = str(row.get("reference", "")).strip(), str(row.get("hypothesis", "")).strip()
        if not truth or len(truth) > 4000 or len(hypothesis) > 4000:
            raise ValueError("Each annotated utterance requires a bounded nonempty reference")
        group = groups.setdefault(language, {
            "samples": 0, "words": 0, "word_errors": 0,
            "graphemes": 0, "grapheme_errors": 0, "command_cases": 0,
            "missed_command_cases": 0, "false_command_cases": 0,
            "language_trials": 0, "language_correct": 0, "latencies_ms": []
        })
        gw, pw = normalized_words(truth), normalized_words(hypothesis)
        cg, pg = graphemes(truth), graphemes(hypothesis)
        if not gw or not cg:
            raise ValueError("Reference cannot contain only punctuation")
        group["samples"] += 1
        group["words"] += len(gw)
        group["word_errors"] += edit_counts(gw, pw)["distance"]
        group["graphemes"] += len(cg)
        group["grapheme_errors"] += edit_counts(cg, pg)["distance"]
        reference_commands, actual_commands = command_terms(truth), command_terms(hypothesis)
        if reference_commands:
            group["command_cases"] += 1
            if not reference_commands.issubset(actual_commands):
                group["missed_command_cases"] += 1
        if actual_commands - reference_commands:
            group["false_command_cases"] += 1
        detected = row.get("detected_language")
        if detected is not None and language in {"en", "hi"}:
            group["language_trials"] += 1
            if detected == language:
                group["language_correct"] += 1
        latency = row.get("latency_ms")
        if latency is not None:
            if not isinstance(latency, (float, int)) or not math.isfinite(latency) or latency < 0:
                raise ValueError("Invalid recorded latency")
            group["latencies_ms"].append(float(latency))

    def finish(data: dict[str, Any]) -> dict[str, Any]:
        ordered = sorted(data["latencies_ms"])
        return {
            "samples": data["samples"],
            "reference_words": data["words"],
            "wer": round(data["word_errors"] / data["words"], 4),
            "cer_grapheme": round(data["grapheme_errors"] / data["graphemes"], 4),
            "command_cases": data["command_cases"],
            "missed_command_cases": data["missed_command_cases"],
            "false_command_cases": data["false_command_cases"],
            "language_detection_trials": data["language_trials"],
            "language_detection_accuracy": (round(data["language_correct"] / data["language_trials"], 4)
                                            if data["language_trials"] else None),
            "latency_p50_ms": (round(statistics.median(ordered), 1) if ordered else None),
            "latency_p95_ms": (round(ordered[max(0, math.ceil(.95 * len(ordered)) - 1)], 1)
                               if ordered else None),
        }
    report = {key: finish(value) for key, value in sorted(groups.items())}
    grand = {
        field: sum(row[field] for row in groups.values())
        for field in ("samples", "words", "word_errors", "graphemes", "grapheme_errors",
                      "command_cases", "missed_command_cases", "false_command_cases",
                      "language_trials", "language_correct")
    }
    all_latencies = [latency for row in groups.values() for latency in row["latencies_ms"]]
    grand["latencies_ms"] = all_latencies
    result = {
        "provenance": provenance,
        "overall": finish(grand),
        "by_language": report,
        "metric_notes": "WER and grapheme CER are edit-distance errors divided by reference length; values can exceed 1. Voice confidence is not a measured accuracy score.",
        "privacy": "Aggregated metrics only; original transcripts and audio are never written to the report.",
    }
    return result


def run_manifest(path: Path, transcribe: bool = False) -> dict[str, Any]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("Manifest must contain a list")
    source = "held_out_audio" if transcribe else "labeled_text_metric_sanity_only"
    if transcribe:
        # This mode uses the same exact local Faster-Whisper service as the API.
        # Samples may only resolve within the private manifest directory.
        import time
        from app.services.speech_recognition_service import FasterWhisperSpeechRecognitionService
        stt = FasterWhisperSpeechRecognitionService()
        base = path.resolve().parent
        for row in entries:
            raw = row.get("audio")
            if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
                raise ValueError("Real benchmark requires relative paths for every audio sample")
            audio = (base / raw).resolve()
            if not audio.is_relative_to(base) or not audio.is_file():
                raise ValueError("Audio missing or outside the private benchmark directory")
            if audio.stat().st_size > 25 * 1024 * 1024:
                raise ValueError("Benchmark audio exceeds 25 MB")
            start = time.perf_counter()
            recognized = stt._transcribe_sync(audio, None)
            row["hypothesis"] = recognized.transcript
            row["detected_language"] = recognized.language
            row["latency_ms"] = round((time.perf_counter() - start) * 1000)
    elif any("audio" in item for item in entries):
        raise ValueError("Audio manifest requires --transcribe; refusing to use stale predictions")
    return evaluate(entries, provenance=source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score annotated private WorkMate speech")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--transcribe", action="store_true", help="Run local STT on held-out private audio")
    parser.add_argument("--output", type=Path, help="Optional aggregate-only JSON output")
    args = parser.parse_args()
    result = run_manifest(args.manifest, transcribe=args.transcribe)
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
