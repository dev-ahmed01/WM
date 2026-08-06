"""Pydantic schemas for OWD enterprise workflows, versions, states, steps, uploads, and compilation reports."""

from typing import Optional, List
from pydantic import BaseModel, Field


class KnowledgeItemBase(BaseModel):
    title: str
    department_id: str


class UpdateKnowledgeItemRequest(BaseModel):
    title: Optional[str] = None
    department_id: Optional[str] = None


class WorkflowStateResponse(BaseModel):
    id: str
    state_key: str
    state_type: str
    title: str
    description: Optional[str] = None
    is_initial: bool = False
    is_terminal: bool = False
    ordinal_index: int = 0


class WorkflowStepResponse(BaseModel):
    id: str
    state_id: str
    step_code: str
    instruction: str
    ai_guidance_prompt: Optional[str] = None
    expected_output_type: Optional[str] = None
    is_mandatory: bool = True
    ordinal_index: int = 0


class KnowledgeVersionResponse(BaseModel):
    id: str
    knowledge_item_id: str
    workflow_id: Optional[str] = None
    version_number: int
    semantic_version: Optional[str] = "1.0.0"
    stage_file_uri: str
    ast_hash: Optional[str] = None
    status: str
    created_at: str
    published_at: Optional[str] = None


class KnowledgeItemResponse(BaseModel):
    id: str
    title: str
    department_id: str
    created_by: str
    created_at: str
    workflow_code: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = "OPERATIONAL"
    updated_at: Optional[str] = None


class KnowledgeItemDetailResponse(BaseModel):
    item: KnowledgeItemResponse
    latest_version: Optional[KnowledgeVersionResponse] = None
    published_version: Optional[KnowledgeVersionResponse] = None
    states: List[WorkflowStateResponse] = Field(default_factory=list)


class PaginatedKnowledgeItemsResponse(BaseModel):
    items: List[KnowledgeItemDetailResponse]
    total: int
    page: int
    limit: int


class KnowledgeVersionHistoryResponse(BaseModel):
    knowledge_item_id: str
    versions: List[KnowledgeVersionResponse]


class IngestionStatusResponse(BaseModel):
    knowledge_item_id: str
    version_id: str
    version_number: int
    status: str
    updated_at: str


class UploadResponse(BaseModel):
    knowledge_item_id: str
    version_id: str
    version_number: int
    status: str
    stage_file_uri: str
    message: str = "OWD file successfully validated, compiled, and deployed into Snowflake."

    # OWD Compilation & Deployment Report
    compilation_status: str = "SUCCESS"
    validation_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    number_of_states: int = 0
    number_of_steps: int = 0
    number_of_decisions: int = 0
    number_of_business_rules: int = 0
    number_of_safety_rules: int = 0
    number_of_validation_rules: int = 0
    deployment_status: str = "PUBLISHED"
    snowflake_tables_updated: List[str] = Field(default_factory=list)


class KnowledgeDeleteResponse(BaseModel):
    id: str
    message: str = "Workflow item soft-deleted (version status set to archived)."
