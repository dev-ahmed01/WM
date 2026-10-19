"""Administrator-only source-to-draft SOP editing. Nothing publishes implicitly."""
from __future__ import annotations
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from pydantic import BaseModel,ConfigDict,Field
from starlette.concurrency import run_in_threadpool
from app.middleware.rbac_middleware import require_role
from app.services.document_extraction import (
    DocumentExtractionError, MAX_DOCUMENT_BYTES, extract_document,
)
from app.repositories.procedure_draft_repository import (
    ProcedureDraftRepository,DraftNotFound,DraftConflict,
)

router=APIRouter(prefix="/procedure/drafts",tags=["Procedure Studio"])


class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class DraftStep(Strict):
    id: str=Field(min_length=4,max_length=40)
    instruction: str=Field(min_length=10,max_length=700)
    source_line: int | None=Field(default=None,ge=1)
    reviewed: bool=False


class DraftUpdate(Strict):
    expected_revision: int=Field(ge=1)
    title: str=Field(min_length=5,max_length=180)
    steps: list[DraftStep]=Field(min_length=1,max_length=50)


class DraftReview(Strict):
    expected_revision: int=Field(ge=1)


def _identity(user):
    dept=str(user.get("department_id") or "")
    actor=str(user.get("sub") or "")
    if not dept or not actor:
        raise HTTPException(401,detail={"error_code":"PROCEDURE_IDENTITY_REQUIRED"})
    return dept,actor


async def _call(method,*args):
    try:
        return await run_in_threadpool(method,*args)
    except DraftNotFound as exc:
        raise HTTPException(404,detail={"error_code":"DRAFT_NOT_FOUND"}) from exc
    except DraftConflict as exc:
        raise HTTPException(409,detail={"error_code":"DRAFT_REVIEW_REQUIRED","message":str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(503,detail={"error_code":"PROCEDURE_STUDIO_UNAVAILABLE",
                                        "message":"The draft operation was not saved."}) from exc


@router.post("/import",status_code=201)
async def import_procedure(
    file:UploadFile=File(...),
    title:str=Form(...,min_length=5,max_length=180),
    user:dict=Depends(require_role("admin")),
):
    dept,actor=_identity(user)
    raw=await file.read(MAX_DOCUMENT_BYTES+1)
    if len(raw)>MAX_DOCUMENT_BYTES:
        raise HTTPException(413,detail={"error_code":"SOURCE_TOO_LARGE"})
    try:
        extracted=await run_in_threadpool(extract_document,file.filename or "",raw)
    except DocumentExtractionError as exc:
        raise HTTPException(422,detail={"error_code":"DOCUMENT_EXTRACTION_FAILED",
                                        "message":str(exc)}) from exc
    return await _call(ProcedureDraftRepository.create,dept,actor,extracted,raw,title)


@router.get("")
async def list_procedure_drafts(
    user:dict=Depends(require_role("admin")),
):
    dept,_=_identity(user)
    return {"items":await _call(ProcedureDraftRepository.list,dept)}


@router.get("/{draft_id}")
async def get_procedure_draft(
    draft_id:str,
    user:dict=Depends(require_role("admin")),
):
    dept,_=_identity(user)
    return await _call(ProcedureDraftRepository.get,dept,draft_id)


@router.put("/{draft_id}")
async def update_procedure_draft(
    draft_id:str,payload:DraftUpdate,
    user:dict=Depends(require_role("admin")),
):
    dept,actor=_identity(user)
    return await _call(
        ProcedureDraftRepository.update,dept,actor,draft_id,
        payload.expected_revision,payload.title,
        [s.model_dump() for s in payload.steps],
    )


@router.post("/{draft_id}/review")
async def review_procedure_draft(
    draft_id:str,payload:DraftReview,
    user:dict=Depends(require_role("admin")),
):
    dept,actor=_identity(user)
    return await _call(ProcedureDraftRepository.review,dept,actor,draft_id,
                       payload.expected_revision)
