# Pydantic Schemas for Escalations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class EscalationCreate(BaseModel):
    conversation_message_id: str = Field(..., description="ID of the low-confidence Copilot response message")
    reason: str = Field(..., description="Reason for escalation (e.g. LOW_CONFIDENCE, UNGROUNDED)")

class EscalationResolve(BaseModel):
    resolution_note: str = Field(..., description="Supervisor notes on how the issue was resolved")

class EscalationResponse(BaseModel):
    id: str
    conversation_message_id: str
    reason: str
    status: str  # 'open', 'notified', 'resolved', 'closed'
    notified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class EscalationListResponse(BaseModel):
    escalations: List[EscalationResponse]
    total_count: int
