"""Voice for employees: transcribe a recording for review, read an answer aloud, translate an answer to Hindi.

Authentication is required for every route. Nothing is stored: a recording becomes text the employee can edit, and that
text only reaches the assistant when they send it through the normal chat route (which applies all grounding/safety rules).
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.middleware.auth_middleware import get_current_user
from app.services import voice_service
from app.services.voice_service import VoiceError

router = APIRouter(prefix="/voice", tags=["Voice"])


def _fail(exc: VoiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error_code": exc.code, "message": str(exc)})


def _require_enabled() -> None:
    if not settings.VOICE_ENABLED:
        raise HTTPException(status_code=503, detail={"error_code": "VOICE_DISABLED", "message": "Voice is switched off."})


@router.get("/status")
async def voice_status(user: Any = Depends(get_current_user)) -> Dict[str, Any]:
    return voice_service.status()


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("auto"), user: Any = Depends(get_current_user)):
    _require_enabled()
    data = await audio.read(settings.VOICE_MAX_AUDIO_BYTES + 1)
    try:
        return await voice_service.transcribe(data, language)
    except VoiceError as exc:
        return _fail(exc)


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=6000)
    language: str = Field(pattern="^(en|hi)$")


@router.post("/speak")
async def speak(body: SpeakRequest, user: Any = Depends(get_current_user)):
    _require_enabled()
    try:
        wav = await voice_service.synthesize(body.text, body.language)
    except VoiceError as exc:
        return _fail(exc)
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)
    target: str = Field(default="hi", pattern="^hi$")


@router.post("/translate")
async def translate(body: TranslateRequest, user: Any = Depends(get_current_user)):
    _require_enabled()
    try:
        return {"language": "hi", "text": await voice_service.translate_to_hindi(body.text)}
    except VoiceError as exc:
        return _fail(exc)
