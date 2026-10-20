"""Read-only contextual guidance for an active, permission-scoped work assignment.

The published SOP state machine remains the ONLY source of executable authority.
A language model, retrieved reference, or user prompt cannot record a checkpoint.
"""
from __future__ import annotations

from typing import Any

from app.services.reference_answer import ReferenceAnswerService

_GUIDANCE_STATES = frozenset({"active", "paused", "blocked", "ready", "completed"})
_KIND_TO_NAME = {
    "PHOTO_JPEG": "a JPEG photograph",
    "DOCUMENT_PDF": "a PDF document",
    "SUPERVISOR_APPROVAL": "supervisor approval (not automatically verifiable)",
    "DIGITAL_SIGNATURE": "a digital signature (requires specialist verification)",
    "CHECKSUM_HASH": "an independently verified checksum",
}
_OUTPUT_TO_NAME = {
    "CONFIRMATION": "confirm the checkpoint",
    "TEXT_INPUT": "record a written observation",
    "NUMERIC_INPUT": "record a numerical value",
    "DOCUMENT_UPLOAD": "submit the required document",
    "SINGLE_CHOICE": "choose the published option",
    "MULTI_CHOICE": "choose the required published options",
}


def _citation(position:dict[str,Any], excerpt:str) -> dict[str,str] | None:
    step=position.get("step")
    state=position.get("state")
    if not state or not position.get("workflow_version_id") or not excerpt:
        return None
    return {
        "source_type": "published_sop",
        "workflow_version_id": str(position["workflow_version_id"]),
        "state_id": str(state["id"]),
        "step_id": str(step["id"]) if step else "",
        "excerpt": excerpt[:700],
    }


def _answer(position:dict[str,Any], intent:str) -> dict[str,Any]:
    status=position["status"]
    step=position.get("step")
    state=position.get("state")
    blocked=status=="blocked"
    result={"answer":"","citations":[],"requires_supervisor":False,
            "read_only":True,"status":status,
            "workflow_version_id":position.get("workflow_version_id")}
    if blocked:
        result["answer"]=(
            "This assignment is blocked. Stop work and contact the supervisor. "
            "The original SOP execution cannot be restarted or completed from guidance."
        )
        if position.get("case_id"):
            result["answer"]+=" Supervisor case: "+str(position["case_id"])+"."
        result["requires_supervisor"]=True
        if state:
            citation=_citation(position,str(state.get("title") or ""))
            if citation:
                result["citations"]=[citation]
        return result
    if status=="completed":
        result["answer"]="The published workflow has already been recorded as completed. Guidance cannot change that record."
        return result
    if status=="ready":
        result["answer"]="This task is linked to a published SOP. Start guided work to view its first checkpoint."
        return result
    if not step:
        if position.get("decision_options"):
            question=str(position.get("decision_question") or state.get("title") or "")
            result["answer"]=question+"\nSelect only the outcome you actually observed. This assistant cannot select it for you."
            citation=_citation(position,question)
            result["citations"]=[citation] if citation else []
        else:
            result["answer"]="There is no current executable checkpoint. Follow the workflow controls or contact your supervisor."
            result["requires_supervisor"]=True
        return result
    instruction=str(step.get("instruction") or "").strip()
    citation=_citation(position,instruction)
    if citation:
        result["citations"]=[citation]
    if intent=="evidence":
        evidence=[_KIND_TO_NAME.get(x.get("evidence_type"),str(x.get("evidence_type"))) for x in step.get("evidence_specs",[]) if x.get("is_required")]
        output=_OUTPUT_TO_NAME.get(step.get("expected_output_type"),"provide the published step output")
        result["answer"]="For this checkpoint, "+output+"."
        if evidence:
            result["answer"]+=" Required supporting evidence: "+", ".join(evidence)+"."
        else:
            result["answer"]+=" The published checkpoint has no additional mandatory attachment."
        result["answer"]+=" Submitted evidence is received, not independently verified."
    elif intent=="exception":
        result["answer"]=(
            "If conditions are unsafe, inconsistent or cannot be verified, do not attest this checkpoint. "
            "Use the work screen's stop/report control and contact your supervisor. "
            "This does not bypass required evidence or safety gates."
        )
        result["requires_supervisor"]=True
    else:
        result["answer"]="Current published checkpoint:\n"+instruction
        result["answer"]+="\nRecord it only after completing the work and its required verification."
        if status=="paused":
            result["answer"]+=" The task is currently paused."
    return result


class TaskGuidanceService:
    """Current published-state answers plus separately gated approved references."""

    @classmethod
    async def answer(cls,position:dict[str,Any],department:str,intent:str,question:str="") -> dict[str,Any]:
        if position.get("status") not in _GUIDANCE_STATES:
            raise ValueError("Unknown task status.")
        if intent!="ask":
            return _answer(position,intent)
        if position["status"]=="blocked":
            return _answer(position,"exception")
        # The worker's free-form question can retrieve reference facts, but
        # approved reference docs are never instructions authorizing a transition.
        try:
            response=await ReferenceAnswerService.answer(question,department)
        except Exception:
            response=None
        if response is None or not response.is_grounded or not response.citations:
            result=_answer(position,"current_step")
            result["answer"]=(
                "I could not find an approved reference that answers that question. "
                "The current published SOP remains authoritative. "
                "Ask your supervisor rather than guessing.\n\n"+result["answer"]
            )
            result["requires_supervisor"]=True
            result["reference_grounded"]=False
            return result
        return {
            "answer":response.answer,
            "citations":[{
                "source_type":"approved_reference",
                "document_id":cite.document_id,
                "document_title":cite.document_title,
                "chunk_id":cite.chunk_id,
                "excerpt":cite.excerpt,
            } for cite in response.citations],
            "requires_supervisor":False,"read_only":True,
            "status":position["status"],
            "workflow_version_id":position.get("workflow_version_id"),
            "reference_grounded":True,
        }
