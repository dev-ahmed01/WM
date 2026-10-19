"""Phase 1 operational work queue. Authenticated assignments are only queued,
never auto-completed, auto-executed, or represented as approved SOP steps.
"""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.middleware.rbac_middleware import require_role
from app.repositories.work_item_repository import WorkItemRepository

router = APIRouter(prefix="/work/items", tags=["Work queue"])
WorkType = Literal["receiving","putaway","stock_count","picking","dispatch","other"]
Priority = Literal["standard","high"]


class WorkItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=5,max_length=180)
    work_type: WorkType
    priority: Priority = "standard"
    instructions: str = Field(default="",max_length=1200)
    external_reference: str = Field(default="",max_length=100)
    assigned_to: str | None = Field(default=None,max_length=64)


def context(user: dict) -> tuple[str, str, bool]:
    department = str(user.get("department_id") or "")
    actor = str(user.get("sub") or "")
    if not department or not actor:
        raise HTTPException(401,detail={"error_code":"WORK_IDENTITY_REQUIRED"})
    return department,actor,user.get("role") in ("admin","manager")


@router.post("",status_code=201)
async def create_work_item(
    payload: WorkItemCreate,
    user: dict = Depends(require_role("admin","manager"))
) -> dict:
    department,actor,_ = context(user)
    try:
        result = await run_in_threadpool(
            WorkItemRepository.create,department,actor,payload.title.strip(),
            payload.work_type,payload.priority,payload.instructions.strip(),
            payload.external_reference.strip(),payload.assigned_to or None
        )
    except Exception as exc:
        raise HTTPException(503, detail={
          "error_code":"WORK_QUEUE_STORE_UNAVAILABLE",
          "message":"Work could not be queued. No workflow state was changed.",
        }) from exc
    if result is None:
        raise HTTPException(422, detail={
          "error_code":"INVALID_ASSIGNEE",
          "message":"The selected assignee is not active in your department.",
        })
    return result


@router.get("")
async def list_work_items(
    limit: int = Query(100,ge=1,le=100),
    user: dict = Depends(require_role("admin","manager","employee"))
) -> dict:
    department,actor,can_manage = context(user)
    try:
        items = await run_in_threadpool(
            WorkItemRepository.list,department,actor,can_manage,limit
        )
    except Exception as exc:
        raise HTTPException(503,detail={
          "error_code":"WORK_QUEUE_UNAVAILABLE",
          "message":"Work queue is unavailable.",
        }) from exc
    return {"items":items,"scope":"department" if can_manage else "assigned"}


@router.get("/assignees")
async def list_assignees(
    user: dict = Depends(require_role("manager","admin"))
) -> dict:
    department,_,_=context(user)
    try:
        people = await run_in_threadpool(WorkItemRepository.assignees,department)
    except Exception as exc:
        raise HTTPException(503,detail={"error_code":"WORK_ASSIGNEES_UNAVAILABLE"}) from exc
    return {"items":people}


class WorkAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_to: str = Field(min_length=1,max_length=64)


@router.post("/{item_id}/assign")
async def assign_item(
    item_id: str,
    payload: WorkAssignment,
    user: dict = Depends(require_role("admin","manager"))
) -> dict:
    department,actor,_ = context(user)
    try:
        item = await run_in_threadpool(
            WorkItemRepository.assign,department,actor,item_id,payload.assigned_to
        )
    except Exception as exc:
        raise HTTPException(503,detail={"error_code":"WORK_ASSIGNMENT_UNAVAILABLE"}) from exc
    if not item:
        raise HTTPException(409,detail={
            "error_code":"WORK_ASSIGNMENT_REJECTED",
            "message":"Work must be queued or ready, and the assignee active in your department.",
        })
    return item


@router.get("/{item_id}")
async def get_work_item(
    item_id: str,
    user: dict = Depends(require_role("admin","manager","employee"))
) -> dict:
    department,actor,can_manage = context(user)
    try:
        result = await run_in_threadpool(
            WorkItemRepository.get,department,actor,can_manage,item_id
        )
    except Exception as exc:
        raise HTTPException(503,detail={"error_code":"WORK_ITEM_UNAVAILABLE"}) from exc
    if not result:
        raise HTTPException(404,detail={"error_code":"WORK_ITEM_NOT_FOUND"})
    return result
