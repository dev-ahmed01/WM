"""Governed reference documents: separate from executable OWD publication routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.middleware.rbac_middleware import require_role
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.reference_document_repository import (
    ReferenceDocumentRepository, new_reference_id,
)
from app.services.reference_retrieval import ReferenceRetrievalService
from app.services.document_extraction import (
    DocumentExtractionError, MAX_DOCUMENT_BYTES, extract_document,
)
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/knowledge/references", tags=["Reference Knowledge"])
logger = logging.getLogger("workmate.references")


def _problem(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={
        "error_code": code, "message": message, "details": None,
    })


@router.post("", dependencies=[Depends(require_role("admin"))], status_code=201)
async def upload_reference(
    file: UploadFile = File(...),
    department_id: str = Form(...),
    title: str = Form(...),
    current_user: dict = Depends(require_role("admin")),
) -> dict:
    if not title.strip() or len(title.strip()) > 512:
        raise _problem(422, "INVALID_TITLE", "Document title must be 1–512 characters.")
    raw = await file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        extracted = await run_in_threadpool(extract_document, file.filename or "", raw)
    except DocumentExtractionError as exc:
        raise _problem(422, "DOCUMENT_EXTRACTION_FAILED", str(exc)) from exc
    try:
        if not KnowledgeRepository.department_exists(department_id):
            raise _problem(422, "INVALID_DEPARTMENT", "Select an active department.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Reference department lookup failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Could not validate the department.") from exc

    document_id = new_reference_id()
    try:
        stage_uri = IngestionService.stage_reference_file(
            raw, extracted.filename, department_id, document_id,
        )
    except Exception as exc:
        logger.exception("Reference staging failed")
        raise _problem(502, "REFERENCE_STAGE_FAILED", "Could not securely store this document.") from exc

    try:
        saved = ReferenceDocumentRepository.save_draft(
            document_id=document_id, department_id=department_id,
            title=title.strip(), filename=extracted.filename, file_type=extracted.file_type,
            mime_type=(file.content_type or "application/octet-stream")[:128],
            stage_uri=stage_uri, raw=raw,
            extracted_text=extracted.content, warnings=extracted.warnings,
            created_by=str(current_user["sub"]),
        )
    except Exception as exc:
        logger.exception("Reference metadata storage failed; compensating staged upload")
        try:
            IngestionService.remove_staged_files([stage_uri])
        except Exception:
            logger.exception("Orphaned staged reference requires operator cleanup")
        raise _problem(502, "REFERENCE_STORE_FAILED", "Could not register this document. No knowledge was approved.") from exc

    return saved


@router.get("", dependencies=[Depends(require_role("admin"))])
async def list_references(
    department_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(50, ge=1, le=100),
) -> dict:
    try:
        items = ReferenceDocumentRepository.list_documents(department_id, limit=limit)
        return {"items": items, "total": len(items)}
    except Exception as exc:
        logger.exception("Reference listing failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Could not list documents.") from exc


@router.get("/search", dependencies=[Depends(require_role("admin", "manager", "employee"))])
async def search_references(
    q: str = Query(..., min_length=2, max_length=300),
    limit: int = Query(5, ge=1, le=20),
    current_user: dict = Depends(require_role("admin", "manager", "employee")),
) -> dict:
    """Cannot accept a department override from an employee or manager."""
    department_id = str(current_user.get("department_id") or "")
    if not department_id:
        raise _problem(403, "DEPARTMENT_UNAVAILABLE", "No department is assigned to this user.")
    try:
        sources = await ReferenceRetrievalService.search(q, department_id, limit=limit)
        return {"sources": sources, "query": q, "department_id": department_id}
    except Exception as exc:
        logger.exception("Scoped reference search failed")
        raise _problem(502, "REFERENCE_SEARCH_FAILED", "Reference search is unavailable.") from exc


@router.get("/{document_id}", dependencies=[Depends(require_role("admin"))])
async def get_reference(
    document_id: str,
    department_id: str = Query(..., min_length=1, max_length=64),
) -> dict:
    try:
        row = ReferenceDocumentRepository.get_document(document_id, department_id)
    except Exception as exc:
        logger.exception("Reference lookup failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Reference lookup is unavailable.") from exc
    if not row:
        raise _problem(404, "REFERENCE_NOT_FOUND", "No document exists in that department.")
    return row


@router.get("/{document_id}/content", dependencies=[Depends(require_role("admin"))])
async def get_reference_content(
    document_id: str,
    department_id: str = Query(..., min_length=1, max_length=64),
) -> dict:
    try:
        doc = ReferenceDocumentRepository.get_document(document_id, department_id)
        if doc is None:
            raise _problem(404, "REFERENCE_NOT_FOUND", "No document exists in that department.")
        chunks = ReferenceDocumentRepository.read_chunks(document_id, department_id)
        return {"document": doc, "chunks": chunks, "preview_truncated": len(chunks) < doc["chunk_count"]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Reference content lookup failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Could not load source content.") from exc


@router.post("/{document_id}/approve", dependencies=[Depends(require_role("admin"))])
async def approve_reference(
    document_id: str,
    department_id: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(require_role("admin")),
) -> dict:
    try:
        changed = ReferenceDocumentRepository.change_status(
            document_id, department_id, str(current_user["sub"]), action="approve",
        )
    except Exception as exc:
        logger.exception("Reference approval failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Could not approve this document.") from exc
    if not changed:
        raise _problem(409, "REVIEW_CONFLICT", "Document was not found as a draft in this department.")
    return {"id": document_id, "status": "APPROVED"}


@router.post("/{document_id}/archive", dependencies=[Depends(require_role("admin"))])
async def archive_reference(
    document_id: str,
    department_id: str = Query(..., min_length=1, max_length=64),
    current_user: dict = Depends(require_role("admin")),
) -> dict:
    try:
        changed = ReferenceDocumentRepository.change_status(
            document_id, department_id, str(current_user["sub"]), action="archive",
        )
    except Exception as exc:
        logger.exception("Reference archive failed")
        raise _problem(502, "REFERENCE_BACKEND_UNAVAILABLE", "Could not archive this document.") from exc
    if not changed:
        raise _problem(409, "REVIEW_CONFLICT", "Document was not found as approved in this department.")
    return {"id": document_id, "status": "ARCHIVED"}
