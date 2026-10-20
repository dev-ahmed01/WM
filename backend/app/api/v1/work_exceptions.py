"""Supervisor-only task-bound exception desk. Review is not safety clearance."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from starlette.concurrency import run_in_threadpool
from typing import Literal
from app.middleware.rbac_middleware import require_role
from app.repositories.work_exception_repository import (
    WorkExceptionRepository,CaseNotFound,CaseConflict,
)

router=APIRouter(prefix="/work/exceptions",tags=["Supervisor Exceptions"])


class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")


class CaseClaim(Strict):
    expected_revision:int=Field(ge=1)


class CaseReview(Strict):
    expected_revision:int=Field(ge=1)
    decision:Literal["reviewed","follow_up_requested"]
    review_note:str=Field(min_length=8,max_length=1000)


def who(user):
    department=str(user.get("department_id") or "")
    actor=str(user.get("sub") or "")
    if not department or not actor:
        raise HTTPException(401,detail={"error_code":"CASE_IDENTITY_REQUIRED"})
    return department,actor


async def call(fn,*args):
    try:
        return await run_in_threadpool(fn,*args)
    except CaseNotFound as exc:
        raise HTTPException(404,detail={"error_code":"CASE_NOT_FOUND"}) from exc
    except CaseConflict as exc:
        raise HTTPException(409,detail={"error_code":"CASE_REVIEW_CONFLICT","message":str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(503,detail={
            "error_code":"CASE_SERVICE_UNAVAILABLE",
            "message":"The exception action was not saved. Refresh the case status.",
        }) from exc


@router.get("")
async def cases(limit:int=Query(100,ge=1,le=100),
                user:dict=Depends(require_role("admin","manager"))):
    department,_=who(user)
    return {"items":await call(WorkExceptionRepository.list,department,limit)}


@router.get("/{case_id}")
async def case_details(case_id:str,
                       user:dict=Depends(require_role("admin","manager"))):
    department,_=who(user)
    return await call(WorkExceptionRepository.get,department,case_id)


@router.post("/{case_id}/claim")
async def claim_case(case_id:str,payload:CaseClaim,
                     user:dict=Depends(require_role("admin","manager"))):
    department,actor=who(user)
    return await call(WorkExceptionRepository.claim,department,actor,
                      case_id,payload.expected_revision)


@router.post("/{case_id}/review")
async def review_case(case_id:str,payload:CaseReview,
                      user:dict=Depends(require_role("admin","manager"))):
    department,actor=who(user)
    return await call(WorkExceptionRepository.review,department,actor,
                      case_id,payload.expected_revision,
                      payload.decision,payload.review_note)
