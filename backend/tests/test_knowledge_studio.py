"""Knowledge ingestion API tests for the deterministic OWD pipeline."""

from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.knowledge_studio import router as knowledge_router
from app.core.security import create_access_token
from app.services.ingestion import IngestionService


app = FastAPI()
app.include_router(knowledge_router, prefix="/api/v1")
client = TestClient(app)
ADMIN_TOKEN = create_access_token(user_id="usr_admin001", role="admin", department_id="dept_admin")
EMPLOYEE_TOKEN = create_access_token(user_id="usr_emp001", role="employee", department_id="dept_eng")
OWD_BYTES = Path("backend/tests/fixtures/owd_repository/inbound/receive_shipment_v1_1.md").read_bytes()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upload_is_admin_only():
    response = client.post(
        "/api/v1/knowledge/upload", headers=headers(EMPLOYEE_TOKEN),
        data={"department_id": "dept_inbound", "title": "Receive Shipment"},
        files={"file": ("receive.md", OWD_BYTES, "text/markdown")},
    )
    assert response.status_code == 403


def test_upload_rejects_non_markdown_before_staging():
    with patch.object(IngestionService, "stage_file") as stage:
        response = client.post(
            "/api/v1/knowledge/upload", headers=headers(ADMIN_TOKEN),
            data={"department_id": "dept_inbound", "title": "Invalid"},
            files={"file": ("invalid.pdf", b"%PDF", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_FILE_TYPE"
    stage.assert_not_called()


def test_invalid_owd_returns_422_without_staging():
    with patch.object(IngestionService, "stage_file") as stage:
        response = client.post(
            "/api/v1/knowledge/upload", headers=headers(ADMIN_TOKEN),
            data={"department_id": "dept_inbound", "title": "Invalid"},
            files={"file": ("invalid.md", b"# ordinary markdown", "text/markdown")},
        )
    assert response.status_code == 422
    stage.assert_not_called()


@patch("app.api.v1.knowledge_studio.KnowledgeRepository.department_exists", return_value=True)
@patch("app.api.v1.knowledge_studio.KnowledgeRepository.get_next_version_number", return_value=3)
@patch.object(IngestionService, "stage_file", return_value="@RAW_OWD_STAGE/SOP_INB_001/v3/hash/receive.md")
@patch("app.api.v1.knowledge_studio.OWDCompilerPipeline.process_owd")
def test_upload_uses_server_version_and_publishes(process, stage, next_version, department_exists):
    process.return_value = {
        "compilation_status": "SUCCESS", "deployment_status": "PUBLISHED",
        "workflow_id": "workflow-id", "version_id": "version-id",
        "validation_errors": [], "warnings": [], "number_of_states": 4, "number_of_steps": 8,
    }
    response = client.post(
        "/api/v1/knowledge/upload", headers=headers(ADMIN_TOKEN),
        data={"department_id": "dept_inbound", "title": "Receive Shipment"},
        files={"file": ("receive.md", OWD_BYTES, "text/markdown")},
    )
    assert response.status_code == 200
    assert response.json()["version_number"] == 3
    assert process.call_args.kwargs["version_number"] == 3
    assert process.call_args.kwargs["prepared_document"].workflow.version_number == 3
    stage.assert_called_once()


def test_legacy_ingestion_callback_is_removed():
    response = client.post("/api/v1/knowledge/anything/ingestion-callback", json={})
    assert response.status_code == 404
