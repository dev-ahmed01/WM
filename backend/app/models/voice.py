"""Schemas for authenticated multilingual Copilot voice interactions."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.copilot import CopilotResponse


VoiceLanguage = Literal["auto", "en", "hi"]


class TranscriptionResult(BaseModel):
    transcript: str
    language: str
    confidence: float = Field(ge=0.0, le=1.0)


class VoiceCopilotResponse(BaseModel):
    language: str
    transcript: str
    translated_transcript: str
    response_text: str
    audio_url: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    transcription_ms: int
    translation_ms: int
    synthesis_ms: int
    copilot: CopilotResponse


class VoiceSynthesisRequest(BaseModel):
    response_message_id: str = Field(min_length=1, max_length=64)


class VoiceSynthesisResponse(BaseModel):
    audio_url: str
    synthesis_ms: int
