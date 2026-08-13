"""Knowledge Studio API v1 router.

Provides enterprise OWD workflow upload, compilation, staging, version tracking, graph detail queries,
metadata edits, and soft-delete. Protected by admin RBAC.
"""

import logging
import hashlib
from typing import Optional, Dict, Any, List
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    HTTPException,
    Query,
    status,
)

from app.middleware.rbac_middleware import require_role
from app.services.ingestion import IngestionService
from app.repositories.knowledge_repository import KnowledgeRepository
from app.compiler.pipeline import OWDCompilerPipeline
from app.compiler.exceptions import OWDLoaderException, OWDParsingException
from app.compiler.parser import OWDParser
from app.compiler.validator import OWDValidator
from app.compiler.utils import generate_deterministic_uuid
from app.exceptions import WorkMateException
from app.integrations.ai_gateway import AIGateway
from app.models.knowledge import (
    UploadResponse,
    PaginatedKnowledgeItemsResponse,
    KnowledgeItemDetailResponse,
    KnowledgeItemResponse,
    KnowledgeVersionHistoryResponse,
    IngestionStatusResponse,
    UpdateKnowledgeItemRequest,
    KnowledgeDeleteResponse,
    KnowledgePermanentDeleteRequest,
    KnowledgePermanentDeleteResponse,
    KnowledgeVersionResponse,
    WorkflowStateResponse,
)

ingestion_logger = logging.getLogger("ingestion_jobs")

router = APIRouter(prefix="/knowledge", tags=["Knowledge Studio"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def upload_knowledge(
    file: UploadFile = File(...),
    department_id: str = Form(...),
    title: str = Form(...),
    knowledge_item_id: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(require_role("admin")),
) -> UploadResponse:
    """Validates uploaded OWD markdown file, stages file in Snowflake Stage, compiles markdown into normalized state machine graph, persists structures into KNOWLEDGE_STUDIO tables, and returns detailed compilation report."""
    # 1. Validate file extension and size (<= 25MB)
    IngestionService.validate_upload(file)

    # Read once; only strict UTF-8 OWD Markdown is accepted.
    file.file.seek(0)
    raw_bytes = file.file.read()
    file.file.seek(0)

    try:
        content_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_ENCODING", "message": "OWD Markdown must be UTF-8 encoded.", "details": None},
        )

    # Parse and validate before creating any staged or database artifact.
    try:
        prepared_document = OWDParser.parse(
            markdown_text=content_text,
            title=title,
            department_id=department_id,
            default_version=1,
        )
    except OWDParsingException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "OWD_PARSING_FAILED", "message": exc.message, "details": None},
        ) from exc

    validation = OWDValidator.validate(prepared_document)
    if not validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "OWD_VALIDATION_FAILED", "message": "OWD validation failed.", "details": validation.errors},
        )

    workflow_code = prepared_document.workflow.workflow_code
    workflow_id = generate_deterministic_uuid("workflow", workflow_code)
    if knowledge_item_id and knowledge_item_id != workflow_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "WORKFLOW_ID_MISMATCH", "message": "The supplied knowledge item does not match the OWD workflow code.", "details": None},
        )

    try:
        department_is_active, version_number = KnowledgeRepository.get_upload_context(
            department_id,
            workflow_id,
        )
        if not department_is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error_code": "INVALID_DEPARTMENT", "message": f"Unknown or inactive department '{department_id}'.", "details": None},
            )
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "SNOWFLAKE_LOOKUP_FAILED", "message": exc.message, "details": None},
        ) from exc

    prepared_document.workflow.version_number = version_number
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    stage_prefix = f"{workflow_code}/v{version_number}/{source_hash[:12]}"
    try:
        stage_file_uri = IngestionService.stage_file(raw_bytes, file.filename or f"{workflow_code}.md", stage_prefix)
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "SNOWFLAKE_STAGE_FAILED", "message": exc.message, "details": None},
        ) from exc

    user_id = current_user.get("sub", "admin")

    # 4. Execute OWD Compiler Pipeline (Parser -> Validator -> Compiler -> Loader)
    # Compiler generates deterministic workflow_id and version_id, and OWDLoader transactionally MERGEs into Snowflake
    try:
        compilation_report = OWDCompilerPipeline.process_owd(
            markdown_text=content_text,
            title=title,
            department_id=department_id,
            user_id=user_id,
            stage_file_uri=stage_file_uri,
            version_number=version_number,
            prepared_document=prepared_document,
            source_filename=(file.filename or f"{workflow_code}.md").rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        )
    except OWDLoaderException as loader_err:
        ingestion_logger.error(f"[UPLOAD FAILURE] Snowflake database load failed: {loader_err.message}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "SNOWFLAKE_LOAD_FAILED",
                "message": f"Failed to persist compiled OWD workflow into Snowflake: {loader_err.message}",
                "details": None,
            },
        )
    except Exception as exc:
        ingestion_logger.error(f"[UPLOAD FAILURE] OWD Compiler pipeline error: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "COMPILER_PIPELINE_FAILED",
                "message": f"OWD compilation pipeline failed: {str(exc)}",
                "details": None,
            },
        )

    dep_status = compilation_report.get("deployment_status", "PUBLISHED")
    comp_status = compilation_report.get("compilation_status", "SUCCESS")
    if comp_status != "SUCCESS" or dep_status != "PUBLISHED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": comp_status, "message": "OWD ingestion did not complete.", "details": compilation_report.get("validation_errors", [])},
        )
    workflow_id = compilation_report.get("workflow_id", "")
    version_id = compilation_report.get("version_id", "")
    # A publication can move an existing workflow between departments. Clear
    # all disposable retrieval state so neither the old nor new department can
    # observe stale workflow versions.
    AIGateway.invalidate_all()

    return UploadResponse(
        knowledge_item_id=workflow_id,
        version_id=version_id,
        version_number=version_number,
        status="published" if dep_status == "PUBLISHED" else "staged",
        stage_file_uri=stage_file_uri,
        message=f"OWD file successfully compiled and deployed into Snowflake KNOWLEDGE_STUDIO ({compilation_report.get('number_of_states', 0)} states, {compilation_report.get('number_of_steps', 0)} steps).",
        compilation_status=comp_status,
        validation_errors=compilation_report.get("validation_errors", []),
        warnings=compilation_report.get("warnings", []),
        number_of_states=compilation_report.get("number_of_states", 0),
        number_of_steps=compilation_report.get("number_of_steps", 0),
        number_of_decisions=compilation_report.get("number_of_decisions", 0),
        number_of_business_rules=compilation_report.get("number_of_business_rules", 0),
        number_of_safety_rules=compilation_report.get("number_of_safety_rules", 0),
        number_of_validation_rules=compilation_report.get("number_of_validation_rules", 0),
        deployment_status=dep_status,
        snowflake_tables_updated=compilation_report.get("snowflake_tables_updated", []),
    )


@router.get(
    "",
    response_model=PaginatedKnowledgeItemsResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def list_knowledge_items(
    department_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedKnowledgeItemsResponse:
    """Paginated list of enterprise OWD workflows, filterable by department and version status."""
    items_raw, total = KnowledgeRepository.list_items(
        department_id=department_id,
        status_filter=status_filter,
        page=page,
        limit=limit,
    )

    detailed_items = []
    for item in items_raw:
        latest = KnowledgeRepository.get_latest_version(item["id"])
        published = KnowledgeRepository.get_published_version(item["id"])
        detailed_items.append(
            KnowledgeItemDetailResponse(
                item=KnowledgeItemResponse(**item),
                latest_version=KnowledgeVersionResponse(**latest) if latest else None,
                published_version=KnowledgeVersionResponse(**published) if published else None,
            )
        )

    return PaginatedKnowledgeItemsResponse(
        items=detailed_items,
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/departments",
    dependencies=[Depends(require_role("admin"))],
)
async def list_departments() -> List[Dict[str, str]]:
    """Return active departments accepted by the ingestion pipeline."""
    try:
        return KnowledgeRepository.list_departments()
    except WorkMateException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error_code": "SNOWFLAKE_LOOKUP_FAILED", "message": exc.message, "details": None},
        ) from exc


@router.get(
    "/{id}",
    response_model=KnowledgeItemDetailResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_knowledge_item(id: str) -> KnowledgeItemDetailResponse:
    """Retrieves a single OWD workflow by ID along with its states breakdown, published, and latest versions."""
    item = KnowledgeRepository.get_item_by_id(id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow item '{id}' not found in KNOWLEDGE_STUDIO.",
                "details": None,
            },
        )

    latest = KnowledgeRepository.get_latest_version(id)
    published = KnowledgeRepository.get_published_version(id)

    states_raw = []
    active_ver = published or latest
    if active_ver:
        states_raw = KnowledgeRepository.get_workflow_states(active_ver["id"])

    states = [WorkflowStateResponse(**s) for s in states_raw]

    return KnowledgeItemDetailResponse(
        item=KnowledgeItemResponse(**item),
        latest_version=KnowledgeVersionResponse(**latest) if latest else None,
        published_version=KnowledgeVersionResponse(**published) if published else None,
        states=states,
    )


@router.get(
    "/{id}/versions",
    response_model=KnowledgeVersionHistoryResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_version_history(id: str) -> KnowledgeVersionHistoryResponse:
    """Retrieves full version history for an OWD workflow."""
    item = KnowledgeRepository.get_item_by_id(id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow item '{id}' not found.",
                "details": None,
            },
        )

    versions_raw = KnowledgeRepository.get_version_history(id)
    versions = [KnowledgeVersionResponse(**v) for v in versions_raw]

    return KnowledgeVersionHistoryResponse(
        knowledge_item_id=id,
        versions=versions,
    )


@router.get(
    "/{id}/status",
    response_model=IngestionStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_ingestion_status(id: str) -> IngestionStatusResponse:
    """Retrieves current processing status of latest version of an OWD workflow."""
    latest = KnowledgeRepository.get_latest_version(id)
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"No version records found for workflow item '{id}'.",
                "details": None,
            },
        )

    return IngestionStatusResponse(
        knowledge_item_id=id,
        version_id=latest["id"],
        version_number=latest["version_number"],
        status=latest["status"],
        updated_at=latest["created_at"],
    )


@router.put(
    "/{id}",
    response_model=KnowledgeItemResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_knowledge_metadata(
    id: str,
    payload: UpdateKnowledgeItemRequest,
) -> KnowledgeItemResponse:
    """Updates title or department_id metadata of an OWD workflow."""
    if payload.department_id is not None:
        try:
            department_is_active = KnowledgeRepository.department_exists(payload.department_id)
        except WorkMateException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error_code": "SNOWFLAKE_LOOKUP_FAILED", "message": exc.message, "details": None},
            ) from exc
        if not department_is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "INVALID_DEPARTMENT",
                    "message": f"Unknown or inactive department '{payload.department_id}'.",
                    "details": None,
                },
            )
    updated = KnowledgeRepository.update_item_metadata(
        item_id=id,
        title=payload.title,
        department_id=payload.department_id,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow item '{id}' not found.",
                "details": None,
            },
        )
    return KnowledgeItemResponse(**updated)


@router.delete(
    "/{id}",
    response_model=KnowledgeDeleteResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_knowledge_item(id: str) -> KnowledgeDeleteResponse:
    """Soft-deletes an OWD workflow item by setting version status to 'archived'."""
    item = KnowledgeRepository.get_item_by_id(id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow item '{id}' not found.",
                "details": None,
            },
        )

    KnowledgeRepository.soft_delete_item(id)
    return KnowledgeDeleteResponse(id=id)


@router.delete(
    "/{id}/permanent",
    response_model=KnowledgePermanentDeleteResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def permanently_delete_knowledge_item(
    id: str,
    payload: KnowledgePermanentDeleteRequest,
) -> KnowledgePermanentDeleteResponse:
    """Permanently delete one workflow graph after an explicit code confirmation."""
    item = KnowledgeRepository.get_item_by_id(id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOT_FOUND",
                "message": f"Workflow item '{id}' not found.",
                "details": None,
            },
        )

    workflow_code = str(item.get("workflow_code") or "")
    if payload.confirmation.strip() != workflow_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONFIRMATION_MISMATCH",
                "message": f"Type the workflow code '{workflow_code}' exactly to delete it permanently.",
                "details": None,
            },
        )

    result = KnowledgeRepository.permanently_delete_item(str(item["id"]))
    stage_files_deleted = 0
    stage_cleanup_warning = None
    try:
        stage_files_deleted = IngestionService.remove_staged_files(
            result.get("stage_file_uris", [])
        )
    except WorkMateException as exc:
        stage_cleanup_warning = exc.message
        ingestion_logger.warning(
            "Workflow '%s' deleted with staged-file cleanup warning",
            item["id"],
        )

    AIGateway.invalidate_department(str(item["department_id"]))
    return KnowledgePermanentDeleteResponse(
        id=str(item["id"]),
        deleted_counts=result.get("deleted_counts", {}),
        stage_files_deleted=stage_files_deleted,
        stage_cleanup_warning=stage_cleanup_warning,
    )
