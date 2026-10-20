"""Supervisor-only task-bound exception desk. Review is not safety clearance."""
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from starlette.concurrency import run_in_threadpool
from typing import Literal
from app.middleware.rbac_middleware import require_role
from app.repositories.work_corrective_repository import CorrectiveWorkRepository
from app.repositories.work_case_closure_repository import CaseClosureRepository
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



class CaseAction(Strict):
    expected_revision:int=Field(ge=1)
    kind:Literal["containment_recorded","remediation_proposed"]
    note:str=Field(min_length=12,max_length=1000)


class ShiftTransfer(Strict):
    recipient_label:str=Field(min_length=2,max_length=100)
    next_action:str=Field(min_length=5,max_length=1500)
    notes:str=Field(default="",max_length=1500)


class CorrectiveRequest(Strict):
    expected_revision:int=Field(ge=1)
    workflow_version_id:str=Field(min_length=4,max_length=64)
    assigned_to:str=Field(min_length=1,max_length=64)
    plan_note:str=Field(min_length=20,max_length=1000)


class CorrectiveDecision(Strict):
    decision:Literal["approved","rejected"]
    decision_note:str=Field(min_length=16,max_length=1000)


class EvidenceReview(Strict):
    expected_revision:int=Field(ge=1)
    review_note:str=Field(min_length=20,max_length=1000)


class SiteAcceptance(Strict):
    expected_revision:int=Field(ge=1)
    site_record_reference:str=Field(min_length=8,max_length=128)
    site_acceptance_note:str=Field(min_length=30,max_length=1000)
    independent_site_inspection_attested:Literal[True]


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

@router.post("/{case_id}/action")
async def record_containment_or_remediation(
    case_id:str,payload:CaseAction,
    user:dict=Depends(require_role("admin","manager")),
):
    department,actor=who(user)
    return await call(WorkExceptionRepository.action,department,actor,case_id,
                      payload.expected_revision,payload.kind,payload.note)


@router.post("/{case_id}/handover",status_code=201)
async def submit_task_shift_handover(
    case_id:str,payload:ShiftTransfer,
    user:dict=Depends(require_role("admin","manager","employee")),
):
    department,actor=who(user)
    return await call(WorkExceptionRepository.handover,department,actor,case_id,
                      payload.recipient_label,payload.next_action,payload.notes)

@router.post("/{case_id}/corrective",status_code=201)
async def request_corrective_task(
    case_id:str,payload:CorrectiveRequest,
    user:dict=Depends(require_role("admin","manager")),
):
    department,actor=who(user)
    return await call(
        CorrectiveWorkRepository.request,department,actor,case_id,
        payload.expected_revision,payload.workflow_version_id,
        payload.assigned_to,payload.plan_note,
    )


@router.post("/{case_id}/corrective/{request_id}/decision")
async def decide_corrective_task(
    case_id:str,request_id:str,payload:CorrectiveDecision,
    user:dict=Depends(require_role("admin")),
):
    department,actor=who(user)
    return await call(
        CorrectiveWorkRepository.decide,department,actor,
        case_id,request_id,payload.decision,payload.decision_note,
    )


@router.post("/{case_id}/closure/evidence",status_code=201)
async def review_corrective_evidence(
    case_id:str,payload:EvidenceReview,
    user:dict=Depends(require_role("admin","manager")),
):
    department,actor=who(user)
    return await call(
        CaseClosureRepository.review_evidence,department,actor,case_id,
        payload.expected_revision,payload.review_note,
    )


@router.post("/{case_id}/closure/site")
async def attest_independent_site_acceptance(
    case_id:str,payload:SiteAcceptance,
    user:dict=Depends(require_role("admin")),
):
    department,actor=who(user)
    return await call(
        CaseClosureRepository.accept_site,department,actor,case_id,
        payload.expected_revision,payload.site_record_reference,
        payload.site_acceptance_note,payload.independent_site_inspection_attested,
    )
