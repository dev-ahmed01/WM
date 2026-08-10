"""Pydantic schemas for persisted OWD workflow execution sessions."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


WorkflowSessionStatus = Literal[
    "active", "paused", "completed", "abandoned", "escalated"
]


class WorkflowSession(BaseModel):
    """Public representation of WORKMATE_COPILOT.workflow_sessions."""

    id: str
    conversation_id: str
    workflow_version_id: str
    current_state_id: str
    previous_state_id: Optional[str] = None
    user_id: str
    status: WorkflowSessionStatus
    session_context: Dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class AbandonSessionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class AdvanceSessionRequest(BaseModel):
    """Structured input used for decision/rule/expression transitions."""

    decision_option: Optional[str] = Field(None, max_length=128)
    rule_results: Dict[str, bool] = Field(default_factory=dict)
    values: Dict[str, Any] = Field(default_factory=dict)
    use_fallback: bool = False


class WorkflowDecisionOption(BaseModel):
    option_code: str
    option_label: str


class WorkflowPosition(BaseModel):
    state_id: str
    state_title: str
    state_type: str
    step_id: Optional[str] = None
    step_number: Optional[int] = None
    step_title: Optional[str] = None
    expected_output_type: Optional[str] = None
    decision_options: List[WorkflowDecisionOption] = Field(default_factory=list)
