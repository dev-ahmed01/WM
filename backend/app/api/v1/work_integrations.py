"""Authenticated adapter-contract inbox for staged WMS/ERP task imports.

There is no publicly accessible webhook in Phase 6A. An authenticated
department manager imports normalized events for a second manager to review.
"""
from __future__ import annotations

from typing import Literal
import json

from fastapi import APIRouter,Depends,HTTPException,Query,Request
from pydantic import BaseModel,ConfigDict,Field,field_validator,ValidationError
from starlette.concurrency import run_in_threadpool
from app.middleware.rbac_middleware import require_role
from app.repositories.work_integration_intake_repository import (
    IntegrationIntakeRepository,IntegrationNotFound,IntegrationConflict,
)

from app.repositories.work_integration_connector_repository import (
    ConnectorRepository,configured_secret,is_signature_valid,ID_PATTERN,MAX_BODY,
)

router=APIRouter(prefix="/work/integrations",tags=["Warehouse integrations"])

class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class IncomingWork(Strict):
    source_system:Literal["sap","oracle","odoo","custom_wms"]
    external_event_id:str=Field(min_length=6,max_length=100,pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    external_work_id:str=Field(min_length=4,max_length=80,pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    title:str=Field(min_length=5,max_length=180)
    work_type:Literal["receiving","putaway","stock_count","picking","dispatch","other"]
    priority:Literal["standard","high"]="standard"
    instructions:str=Field(default="",max_length=1200)
    assigned_to:str|None=Field(default=None,min_length=1,max_length=64)

    @field_validator("title","instructions")
    @classmethod
    def clean_text(cls,value:str):
        value=value.strip()
        if "\x00" in value or False:
            raise ValueError("Invalid task text")
        return value

    @field_validator("title")
    @classmethod
    def require_title(cls,value:str):
        if len(value)<5:
            raise ValueError("Task title is too short")
        return value


class IntakeDecision(Strict):
    decision:Literal["accepted","rejected"]
    decision_note:str=Field(min_length=16,max_length=1000)


def who(user):
    department=str(user.get("department_id") or "")
    actor=str(user.get("sub") or "")
    if not department or not actor:
        raise HTTPException(401,detail={"error_code":"INTEGRATION_IDENTITY_REQUIRED"})
    return department,actor


async def call(fn,*args):
    try:
        return await run_in_threadpool(fn,*args)
    except IntegrationNotFound as exc:
        raise HTTPException(404,detail={"error_code":"INTEGRATION_NOT_FOUND"}) from exc
    except IntegrationConflict as exc:
        raise HTTPException(409,detail={
            "error_code":"INTEGRATION_CONFLICT","message":str(exc),
        }) from exc
    except Exception as exc:
        raise HTTPException(503,detail={
            "error_code":"INTEGRATION_STORE_UNAVAILABLE",
            "message":"No integration decision is confirmed. Refresh before retrying.",
        }) from exc


@router.post("/intake",status_code=201)
async def stage_import(
    payload:IncomingWork,
    user:dict=Depends(require_role("admin","manager")),
):
    dept,actor=who(user)
    return await call(IntegrationIntakeRepository.stage,dept,actor,payload.model_dump())


@router.get("/intake")
async def intake_queue(
    limit:int=Query(100,ge=1,le=100),
    user:dict=Depends(require_role("admin","manager")),
):
    dept,actor=who(user)
    return {"items":await call(IntegrationIntakeRepository.list,dept,actor,limit)}


@router.post("/intake/{intake_id}/decision")
async def decide_import(
    intake_id:str,payload:IntakeDecision,
    user:dict=Depends(require_role("admin","manager")),
):
    dept,actor=who(user)
    return await call(
        IntegrationIntakeRepository.decide,dept,actor,intake_id,
        payload.decision,payload.decision_note,
    )


class NewConnector(Strict):
    id:str=Field(min_length=6,max_length=64,pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{5,63}$")
    source_system:Literal["sap","oracle","odoo","custom_wms"]


class ConnectorControl(Strict):
    enabled:bool


@router.get("/sources")
async def connector_sources(user:dict=Depends(require_role("admin"))):
    dept,actor=who(user)
    return {"items":await call(ConnectorRepository.list,dept,actor)}


@router.post("/sources",status_code=201)
async def register_connector(payload:NewConnector,user:dict=Depends(require_role("admin"))):
    dept,actor=who(user)
    return await call(ConnectorRepository.register,dept,actor,payload.id,payload.source_system)


@router.post("/sources/{source_id}/control")
async def set_connector_control(
    source_id:str,payload:ConnectorControl,user:dict=Depends(require_role("admin")),
):
    dept,actor=who(user)
    return await call(ConnectorRepository.set_enabled,dept,actor,source_id,payload.enabled)


@router.get("/sources/{source_id}/deliveries")
async def source_deliveries(
    source_id:str,limit:int=Query(40,ge=1,le=100),
    user:dict=Depends(require_role("admin")),
):
    dept,actor=who(user)
    return {"items":await call(ConnectorRepository.deliveries,dept,actor,source_id,limit)}


@router.post("/webhooks/{source_id}",status_code=202)
async def receive_signed_webhook(source_id:str,request:Request):
    """Public ingress only with configured signing key, fresh timestamp and nonce.

    All source objects, departments, audit authors and review permission come
    from the registered backend source; never from unauthenticated JSON claims.
    """
    secret=configured_secret(source_id) if ID_PATTERN.fullmatch(source_id) else None
    stamp=request.headers.get("x-wm-timestamp","")
    nonce=request.headers.get("x-wm-nonce","")
    signature=request.headers.get("x-wm-signature","")
    if not secret:
        raise HTTPException(401,detail={"error_code":"WEBHOOK_AUTH_FAILED"})
    # Stream-bounded upload avoids allocating arbitrarily large bodies.
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>MAX_BODY:
            raise HTTPException(413,detail={"error_code":"WEBHOOK_TOO_LARGE"})
    raw=bytes(data)
    if not is_signature_valid(secret,stamp,nonce,raw,signature):
        raise HTTPException(401,detail={"error_code":"WEBHOOK_AUTH_FAILED"})
    source=await call(ConnectorRepository.lookup_active,source_id)
    if source is None:
        raise HTTPException(401,detail={"error_code":"WEBHOOK_AUTH_FAILED"})
    payload=None
    issue=None
    try:
        candidate=json.loads(raw)
        payload=IncomingWork.model_validate(candidate).model_dump()
    except (ValueError,TypeError,ValidationError):
        issue="invalid_schema"
    delivery=await call(ConnectorRepository.deliver,source,nonce,stamp,raw,payload,issue)
    if delivery["status"]=="conflict":
        raise HTTPException(409,detail={"error_code":"WEBHOOK_SOURCE_CONFLICT"})
    if delivery["status"]=="invalid":
        raise HTTPException(422,detail={"error_code":"WEBHOOK_PAYLOAD_INVALID"})
    return delivery
