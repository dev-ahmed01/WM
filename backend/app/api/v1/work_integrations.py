"""Authenticated adapter-contract inbox for staged WMS/ERP task imports.

There is no publicly accessible webhook in Phase 6A. An authenticated
department manager imports normalized events for a second manager to review.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from starlette.concurrency import run_in_threadpool
from app.middleware.rbac_middleware import require_role
from app.repositories.work_integration_intake_repository import (
    IntegrationIntakeRepository,IntegrationNotFound,IntegrationConflict,
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
        if "\x00" in value or (value=="" and cls.__name__=="n/a"):
            raise ValueError("Invalid task text")
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
