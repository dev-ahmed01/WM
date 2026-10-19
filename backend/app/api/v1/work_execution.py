"""Role-scoped API for executing published SOPs on actual assigned work.

Employees can attest individual steps; the server validates current OWD
position and every mandatory evidence specification before durable progress.
"""
from __future__ import annotations

from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from starlette.concurrency import run_in_threadpool
from app.middleware.rbac_middleware import require_role
from app.repositories.work_execution_repository import (
    WorkExecutionRepository,ExecutionConflict,ExecutionNotFound,
)

router=APIRouter(prefix="/work/execution",tags=["Guided Work Execution"])


class StrictBody(BaseModel):
    model_config=ConfigDict(extra="forbid")


class BindRequest(StrictBody):
    workflow_version_id: str=Field(min_length=1,max_length=64)


class FileProof(StrictBody):
    spec_id: str=Field(min_length=1,max_length=64)
    filename: str=Field(min_length=4,max_length=128)
    content_base64: str=Field(min_length=4,max_length=2800000)


class StepProof(StrictBody):
    step_id: str=Field(min_length=1,max_length=64)
    confirmation: bool=False
    text: str=Field(default="",max_length=1500)
    number: float | None=Field(default=None,allow_inf_nan=False)
    evidence_files: list[FileProof]=Field(default_factory=list,max_length=4)


class DecisionProof(StrictBody):
    decision_option: str=Field(min_length=1,max_length=128)


class BlockProof(StrictBody):
    reason: str=Field(min_length=8,max_length=500)


def _who(user):
    dept=str(user.get("department_id") or "")
    actor=str(user.get("sub") or "")
    if not dept or not actor:
        raise HTTPException(401,detail={"error_code":"WORK_IDENTITY_REQUIRED"})
    return dept,actor,user.get("role") in ("admin","manager")


async def _call(fn,*args):
    try:
        return await run_in_threadpool(fn,*args)
    except ExecutionNotFound as exc:
        raise HTTPException(404,detail={"error_code":"WORK_NOT_FOUND"}) from exc
    except ExecutionConflict as exc:
        raise HTTPException(409,detail={"error_code":"WORK_PROGRESSION_BLOCKED","message":str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(503,detail={
            "error_code":"WORK_EXECUTION_UNAVAILABLE",
            "message":"The operation was not saved. Check the current work status.",
        }) from exc


@router.get("/procedures")
async def procedures(user:dict=Depends(require_role("admin","manager"))):
    dept,_,_=_who(user)
    return {"items":await _call(WorkExecutionRepository.procedures,dept)}


@router.post("/{work_id}/bind")
async def bind(work_id:str,payload:BindRequest,
               user:dict=Depends(require_role("admin","manager"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.bind,dept,actor,work_id,payload.workflow_version_id)


@router.get("/{work_id}")
async def position(work_id:str,user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,manager=_who(user)
    return await _call(WorkExecutionRepository.position,dept,actor,manager,work_id)


@router.get("/{work_id}/timeline")
async def timeline(work_id:str,user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,manager=_who(user)
    return {"events":await _call(WorkExecutionRepository.timeline,dept,actor,manager,work_id)}


@router.post("/{work_id}/start")
async def start(work_id:str,user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.start,dept,actor,work_id)


@router.post("/{work_id}/step")
async def record_step(work_id:str,payload:StepProof,
                      user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(
        WorkExecutionRepository.progress,dept,actor,work_id,payload.step_id,
        payload.confirmation,payload.text,payload.number,
        [f.model_dump() for f in payload.evidence_files]
    )


@router.post("/{work_id}/decision")
async def record_decision(work_id:str,payload:DecisionProof,
                          user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.decide,dept,actor,work_id,payload.decision_option)


@router.post("/{work_id}/continue")
async def continue_state(work_id:str,
                         user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.continue_state,dept,actor,work_id)


@router.post("/{work_id}/pause")
async def pause(work_id:str,user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.change_status,dept,actor,work_id,"pause","")


@router.post("/{work_id}/resume")
async def resume(work_id:str,user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.change_status,dept,actor,work_id,"resume","")


@router.post("/{work_id}/block")
async def block(work_id:str,payload:BlockProof,
                user:dict=Depends(require_role("admin","manager","employee"))):
    dept,actor,_=_who(user)
    return await _call(WorkExecutionRepository.change_status,dept,actor,work_id,
                       "block",payload.reason.strip())
