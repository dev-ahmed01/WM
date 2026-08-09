# Pydantic Schemas for Workflow Session State Tracking

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

class WorkflowSession(BaseModel):
    id: str
    conversation_id: str
    workflow_version_id: str = ""
    current_step: int = 0
    status: Literal['active', 'paused', 'completed', 'abandoned']
    abandon_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class AbandonSessionRequest(BaseModel):
    reason: str = Field(..., description="Reason for abandoning the workflow session")

class NextActionResponse(BaseModel):
    action: Literal['proceed_to_step', 'needs_explanation', 'needs_document', 'workflow_complete']
    target_step: Optional[int] = None
    step_title: Optional[str] = None
    total_steps: int
