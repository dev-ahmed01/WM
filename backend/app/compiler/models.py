"""Internal Domain Models for the OWD Knowledge Compiler (v1.1 Specification).

These models represent parsed OWD Abstract Syntax Trees (AST), workflow states,
atomic steps, decision engines, AI conversation layers, user contexts, analytics events,
relationships, references, and normalized compilation payloads.
Independent of database ORM or API schemas.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Section 1: Document Metadata
# -----------------------------------------------------------------------------
class DocumentMetadata(BaseModel):
    """Complete document header metadata (Section 1)."""
    sop_id: str
    version: str = "1.1.0"
    department: str = "dept_operations"
    category: str = "OPERATIONAL_SOP"
    owner: str = "System Admin"
    priority: str = "MEDIUM"
    difficulty: str = "INTERMEDIATE"
    estimated_duration: str = "30 mins"
    roles_allowed: List[str] = Field(default_factory=lambda: ["Employee", "Supervisor", "Admin"])
    required_equipment: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    related_sops: List[str] = Field(default_factory=list)
    review_cycle: str = "ANNUAL"
    effective_date: str = "2026-01-01"


# -----------------------------------------------------------------------------
# Section 2: AI Retrieval Metadata
# -----------------------------------------------------------------------------
class AIRetrievalMetadata(BaseModel):
    """Search & vector indexing metadata (Section 2)."""
    keywords: List[str] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)
    search_phrases: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)
    business_process: str = "Operational Workflow"
    equipment: List[str] = Field(default_factory=list)
    workflow_tags: List[str] = Field(default_factory=list)
    embedding_metadata: Dict[str, Any] = Field(default_factory=dict)
    vector_metadata: Dict[str, Any] = Field(default_factory=dict)
    cortex_search_metadata: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Section 3: Workflow Definition
# -----------------------------------------------------------------------------
class WorkflowDefinition(BaseModel):
    """High-level workflow business objectives & bounds (Section 3)."""
    workflow_objective: str
    business_goal: str
    entry_conditions: List[str] = Field(default_factory=list)
    exit_conditions: List[str] = Field(default_factory=list)
    previous_workflow: Optional[str] = None
    next_workflow: Optional[str] = None
    blocking_workflows: List[str] = Field(default_factory=list)
    optional_workflows: List[str] = Field(default_factory=list)
    expected_business_outcome: str = "Process Completed Successfully"


# -----------------------------------------------------------------------------
# Legacy / Shared Components (Rules, Evidence, Guidance)
# -----------------------------------------------------------------------------
class AIGuidance(BaseModel):
    """Contextual assistance prompt instructions for Copilot."""
    prompt_template: str
    contextual_instructions: Optional[str] = None
    safety_overrides: Optional[List[str]] = Field(default_factory=list)


class Reference(BaseModel):
    """External policy, regulation, or SOP reference citation."""
    ref_id: str
    title: str
    uri: Optional[str] = None
    citation_type: str = "POLICY_DOC"


class BusinessRule(BaseModel):
    """Operational business rule or prerequisite check."""
    rule_code: str
    rule_type: str = "BUSINESS_RULE"  # BUSINESS_RULE, PREREQUISITE, COMPLIANCE_CHECK
    condition_logic: str
    error_message: str


class SafetyRule(BaseModel):
    """Critical safety guardrail or hazard check."""
    rule_code: str
    condition_logic: str
    enforcement_level: str = "HARD_STOP"  # HARD_STOP, WARNING_CONFIRM, SUPERVISOR_OVERRIDE
    error_message: str


class ValidationRule(BaseModel):
    """Data entry input validation specification."""
    rule_code: str
    target_field: str
    validation_regex: Optional[str] = None
    error_message: str


class EvidenceSpec(BaseModel):
    """Required compliance evidence attachment specification."""
    evidence_code: str
    evidence_type: str = "DOCUMENT_PDF"  # DOCUMENT_PDF, PHOTO_JPEG, DIGITAL_SIGNATURE, CHECKSUM_HASH, SUPERVISOR_APPROVAL
    min_size_bytes: Optional[int] = 1024
    is_required: bool = True


# -----------------------------------------------------------------------------
# Section 6: AI Conversation Layer
# -----------------------------------------------------------------------------
class AIConversationLayer(BaseModel):
    """Interactive AI conversation prompts per step (Section 6)."""
    question_ai_should_ask: str
    expected_user_responses: List[str] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)
    fallback_prompt: Optional[str] = None
    coaching_prompt: Optional[str] = None
    escalation_trigger: Optional[str] = None
    confidence_requirements: str = "0.85"
    citation_source: Optional[str] = None


# -----------------------------------------------------------------------------
# Section 5: Step Definition
# -----------------------------------------------------------------------------
class Step(BaseModel):
    """Atomic operational step within a workflow state (Section 5)."""
    step_code: str
    sequence_number: int = 1
    instruction: str
    action: str = ""
    expected_outcome: str = "Step Completed Successfully"
    safety_note: Optional[str] = None
    evidence_required: Optional[str] = None
    estimated_time: str = "5 mins"
    retry_policy: str = "MAX_RETRIES_3"
    completion_criteria: str = "User Confirmation"
    common_failure: Optional[str] = None
    recovery_action: Optional[str] = None
    expected_output_type: str = "CONFIRMATION"  # CONFIRMATION, TEXT_INPUT, SINGLE_CHOICE, MULTI_CHOICE, DOCUMENT_UPLOAD, NUMERIC_INPUT
    is_mandatory: bool = True
    ai_guidance: Optional[AIGuidance] = None
    ai_conversation: Optional[AIConversationLayer] = None
    ordinal_index: int = 0


# -----------------------------------------------------------------------------
# Section 7: Decision Engine
# -----------------------------------------------------------------------------
class DecisionOption(BaseModel):
    """Selectable option within a decision node."""
    option_code: str
    option_label: str
    target_state_key: str
    next_step_code: Optional[str] = None


class DecisionNode(BaseModel):
    """Decision Engine node definition (Section 7)."""
    decision_code: str
    question: str
    options: List[DecisionOption] = Field(default_factory=list)
    alternative_path: Optional[str] = None
    business_rule: Optional[str] = None
    escalation_workflow: Optional[str] = None


# Backward alias
Decision = DecisionNode


# -----------------------------------------------------------------------------
# Section 4: Workflow State
# -----------------------------------------------------------------------------
class Transition(BaseModel):
    """Directed edge between state machine nodes."""
    from_state_key: str
    to_state_key: str
    condition_type: str = "ALWAYS"
    condition_expression: Optional[str] = "ALWAYS"
    priority: int = 10


class State(BaseModel):
    """Node in the OWD Finite State Machine graph (Section 4)."""
    state_key: str
    state_type: str = "ATOMIC_STEP"  # START, ATOMIC_STEP, DECISION, PARALLEL_GATE, ESCALATION, END
    title: str
    purpose: Optional[str] = None
    entry_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    responsible_role: str = "Employee"
    expected_duration: str = "10 mins"
    business_objective: Optional[str] = None
    description: Optional[str] = None
    is_initial: bool = False
    is_terminal: bool = False
    ordinal_index: int = 0
    steps: List[Step] = Field(default_factory=list)
    decisions: List[DecisionNode] = Field(default_factory=list)
    business_rules: List[BusinessRule] = Field(default_factory=list)
    safety_rules: List[SafetyRule] = Field(default_factory=list)
    validation_rules: List[ValidationRule] = Field(default_factory=list)
    evidence_specs: List[EvidenceSpec] = Field(default_factory=list)
    transitions: List[Transition] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Section 8: User Context & Permissions
# -----------------------------------------------------------------------------
class UserContextPermissions(BaseModel):
    """RBAC and user context permissions (Section 8)."""
    roles: List[str] = Field(default_factory=lambda: ["Employee", "Supervisor", "Admin"])
    permissions: List[str] = Field(default_factory=list)
    experience_levels: List[str] = Field(default_factory=lambda: ["JUNIOR", "SENIOR"])
    certifications: List[str] = Field(default_factory=list)
    supported_languages: List[str] = Field(default_factory=lambda: ["en-US"])
    department: str = "dept_operations"


# -----------------------------------------------------------------------------
# Section 9: Analytics Events
# -----------------------------------------------------------------------------
class AnalyticsEvent(BaseModel):
    """Telemetry event trigger definition (Section 9)."""
    event_name: str
    event_trigger: str
    kpis: List[str] = Field(default_factory=list)


class AnalyticsMetadata(BaseModel):
    """Analytics events collection (Section 9)."""
    events: List[AnalyticsEvent] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Section 10: Knowledge Relationships
# -----------------------------------------------------------------------------
class KnowledgeRelationship(BaseModel):
    """Graph edge relationship between SOPs, equipment, or policies (Section 10)."""
    relationship_type: str  # PARENT_SOP, CHILD_SOP, RELATED_SOP, PREVIOUS_SOP, NEXT_SOP, ESCALATION_SOP, EXCEPTION_SOP, REFERENCED_EQUIPMENT, REFERENCED_DOCUMENT, REFERENCED_POLICY
    target_reference: str
    description: Optional[str] = None


# -----------------------------------------------------------------------------
# Section 11: References
# -----------------------------------------------------------------------------
class ReferenceV1_1(BaseModel):
    """Reference document or standard citation (Section 11)."""
    reference_type: str  # PRIMARY_SOURCE, SUPPORTING_SOURCE, OFFICIAL_URL, COMPLIANCE_STANDARD, DOC_SECTION
    title: str
    citation_uri: str


# -----------------------------------------------------------------------------
# Root Workflow Entity & Document AST
# -----------------------------------------------------------------------------
class Workflow(BaseModel):
    """Root Operational Workflow Definition entity."""
    workflow_code: str
    title: str
    department_id: str = "dept_operations"
    category: str = "OPERATIONAL_SOP"
    description: Optional[str] = None
    version_number: int = 1
    states: List[State] = Field(default_factory=list)
    references: List[Reference] = Field(default_factory=list)


class OWDDocument(BaseModel):
    """Unified parsed AST document output from OWD Knowledge Compiler (v1.1 & Legacy)."""
    spec_version: str = "1.1"  # "1.0" (Legacy) or "1.1" (v1.1)
    workflow: Workflow
    metadata: Optional[DocumentMetadata] = None
    retrieval_metadata: Optional[AIRetrievalMetadata] = None
    workflow_definition: Optional[WorkflowDefinition] = None
    user_context: Optional[UserContextPermissions] = None
    analytics: Optional[AnalyticsMetadata] = None
    relationships: List[KnowledgeRelationship] = Field(default_factory=list)
    v1_1_references: List[ReferenceV1_1] = Field(default_factory=list)
    raw_source_hash: str
    parsed_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Enterprise Document Layer Attributes
    raw_markdown: Optional[str] = None
    frontmatter_yaml: Optional[str] = None
    frontmatter: Dict[str, Any] = Field(default_factory=dict)
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    code_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)



# Unified AST Alias
UnifiedAST = OWDDocument


# -----------------------------------------------------------------------------
# Compiler Reports & DB Load Payloads
# -----------------------------------------------------------------------------
class ValidationReport(BaseModel):
    """Validation outcome output from OWDValidator."""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    states_count: int = 0
    steps_count: int = 0
    decisions_count: int = 0
    business_rules_count: int = 0
    safety_rules_count: int = 0
    validation_rules_count: int = 0


# -----------------------------------------------------------------------------
# Section 12: Enterprise Knowledge Document Layer Models
# -----------------------------------------------------------------------------
class KnowledgeDocumentModel(BaseModel):
    """Canonical Enterprise Document Entity Model."""
    id: str
    workflow_id: str
    workflow_version_id: str
    document_name: str
    original_filename: str
    stage_uri: str
    relative_path: Optional[str] = None
    directory: Optional[str] = None
    extension: str = "md"
    mime_type: str = "text/markdown"
    uploaded_at: Optional[str] = None
    file_size_bytes: int = 0
    compression: str = "none"
    encoding: str = "utf-8"
    md5_hash: Optional[str] = None
    sha256_hash: str
    compiler_version: str = "1.1.0"
    parser_version: str = "1.1.0"
    source_type: str = "OWD_MARKDOWN"
    language_code: str = "en-US"
    author: Optional[str] = None
    reviewer: Optional[str] = None
    approval_status: str = "APPROVED"
    tags: List[str] = Field(default_factory=list)
    labels: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class DocumentContentModel(BaseModel):
    """Preserved raw and parsed markdown document contents."""
    id: str
    document_id: str
    workflow_version_id: str
    raw_markdown: str
    normalized_markdown: str
    frontmatter_yaml: Optional[str] = None
    frontmatter_json: Dict[str, Any] = Field(default_factory=dict)
    body_markdown: str
    sections_json: List[Dict[str, Any]] = Field(default_factory=list)
    tables_json: List[Dict[str, Any]] = Field(default_factory=list)
    code_blocks_json: List[Dict[str, Any]] = Field(default_factory=list)
    images_json: List[Dict[str, Any]] = Field(default_factory=list)
    links_json: List[Dict[str, Any]] = Field(default_factory=list)


class DocumentAIMetadataModel(BaseModel):
    """Cortex AI analysis & readability metadata."""
    id: str
    document_id: str
    workflow_version_id: str
    reading_time_minutes: int = 1
    word_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    complexity_score: float = 0.5
    risk_score: float = 0.1
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    entities: Dict[str, Any] = Field(default_factory=dict)
    language_detected: str = "en-US"
    embedding_model: str = "none"
    embedding_version: str = "none"
    chunk_count: int = 0
    average_chunk_size: int = 0
    embedding_status: str = "NOT_REQUIRED"
    evaluation_score: Optional[float] = None
    confidence_score: Optional[float] = None


class DocumentChunkModel(BaseModel):
    """First-Class Vector Chunk Object."""
    id: str
    document_id: str
    workflow_version_id: str
    state_id: Optional[str] = None
    step_id: Optional[str] = None
    chunk_order: int = 0
    character_count: int = 0
    token_count: int = 0
    chunk_content: str
    embedding_ref: str = "none"
    vector_status: str = "NOT_REQUIRED"
    chunk_hash: str
    chunk_type: str = "STATE_STEP"
    section_name: Optional[str] = None


class DocumentLineageModel(BaseModel):
    """Audit lineage for document compilation pipeline."""
    id: str
    document_id: str
    workflow_version_id: str
    stage_file_uri: str
    source_markdown_hash: str
    parser_name: str = "OWDParser"
    ast_hash: str
    compiler_name: str = "OWDCompiler"
    loader_name: str = "OWDLoader"
    status: str = "PUBLISHED"
    executed_by: str = "SYSTEM"
    execution_notes: Optional[str] = None


class CompiledWorkflow(BaseModel):
    """Transformed payload ready for database loading across all 20 tables."""
    workflow_payload: Dict[str, Any]
    version_payload: Dict[str, Any]
    states_payload: List[Dict[str, Any]]
    steps_payload: List[Dict[str, Any]]
    transitions_payload: List[Dict[str, Any]]
    decisions_payload: List[Dict[str, Any]] = Field(default_factory=list)
    decision_options_payload: List[Dict[str, Any]]
    rules_payload: List[Dict[str, Any]]
    evidence_specs_payload: List[Dict[str, Any]]
    ai_conversation_payload: List[Dict[str, Any]] = Field(default_factory=list)
    analytics_payload: List[Dict[str, Any]] = Field(default_factory=list)
    relationships_payload: List[Dict[str, Any]] = Field(default_factory=list)
    references_payload: List[Dict[str, Any]] = Field(default_factory=list)
    role_permissions_payload: List[Dict[str, Any]] = Field(default_factory=list)
    search_metadata_payload: List[Dict[str, Any]]
    # Enterprise Document Payloads
    documents_payload: List[Dict[str, Any]] = Field(default_factory=list)
    contents_payload: List[Dict[str, Any]] = Field(default_factory=list)
    ai_metadata_payload: List[Dict[str, Any]] = Field(default_factory=list)
    chunks_payload: List[Dict[str, Any]] = Field(default_factory=list)
    lineage_payload: List[Dict[str, Any]] = Field(default_factory=list)


class LoadResult(BaseModel):
    """Database persistence outcome from OWDLoader."""
    success: bool
    workflow_id: str
    version_id: str
    tables_updated: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
