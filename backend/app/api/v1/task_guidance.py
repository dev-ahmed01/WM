"""Permission-scoped in-context answers for an individual assigned task.

No model output is allowed to mutate work execution or present unsupported
reference text as an approved operational action.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.middleware.rbac_middleware import require_role
from app.repositories.work_execution_repository import (
    WorkExecutionRepository, ExecutionConflict, ExecutionNotFound,
)
from app.services.task_guidance import TaskGuidanceService

router=APIRouter(prefix="/work/guidance",tags=["Task contextual guidance"])


class TaskQuestion(BaseModel):
    model_config=ConfigDict(extra="forbid")
    intent:Literal["current_step","evidence","exception","ask"]
    question:str=Field(default="",max_length=500)


@router.post("/{work_id}")
async def ask_about_task(
    work_id:str,payload:TaskQuestion,
    user:dict=Depends(require_role("admin","manager","employee")),
):
    department=str(user.get("department_id") or "")
    actor=str(user.get("sub") or "")
    if not department or not actor:
        raise HTTPException(status_code=401,detail={"error_code":"TASK_IDENTITY_REQUIRED"})
    if payload.intent=="ask" and len(payload.question.strip())<4:
        raise HTTPException(status_code=422,detail={"error_code":"TASK_QUESTION_REQUIRED"})
    manager=user.get("role") in ("admin","manager")
    try:
        current=await run_in_threadpool(
            WorkExecutionRepository.position,department,actor,manager,work_id
        )
    except ExecutionNotFound as exc:
        raise HTTPException(status_code=404,detail={"error_code":"WORK_NOT_FOUND"}) from exc
    except ExecutionConflict as exc:
        raise HTTPException(status_code=409,detail={"error_code":"WORK_GUIDANCE_CONFLICT"}) from exc
    except Exception as exc:
        raise HTTPException(status_code=503,detail={"error_code":"WORK_GUIDANCE_UNAVAILABLE"}) from exc
    return await TaskGuidanceService.answer(
        current,department,payload.intent,payload.question.strip()
    )
