# Pydantic Schemas for Copilot Messaging & Response Validation Layer

from datetime import datetime
from typing import Optional, List, Union
from pydantic import BaseModel, Field

class Citation(BaseModel):
    document_id: str
    document_title: str
    version_number: int
    # Search results may identify either a numeric step ordinal or a stable
    # state/step key. Do not coerce UUID-like identifiers to integers.
    step_number: Optional[Union[int, str]] = None
    chunk_id: str
    excerpt: str

class CopilotMessageRequest(BaseModel):
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID or null to create new")
    message: str = Field(..., description="User operational query or step execution response")

class CopilotResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    citations: List[Citation]
    confidence_score: float
    is_grounded: bool
    requires_escalation: bool
    active_sop_id: Optional[str] = None
    active_step_number: Optional[int] = None
    active_step_title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ValidatedResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence_score: float
    is_grounded: bool
    requires_escalation: bool = False

class EscalationRequired(BaseModel):
    answer: str
    reason: str
    confidence_score: float
    requires_escalation: bool = True

class CopilotSessionSummary(BaseModel):
    id: str
    title: str
    status: str
    started_at: str
    last_message_preview: Optional[str] = None

class CopilotHistoryResponse(BaseModel):
    sessions: List[CopilotSessionSummary]
    total: int
