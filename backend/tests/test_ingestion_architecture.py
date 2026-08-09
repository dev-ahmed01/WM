"""Guardrails preserving deterministic OWD ingestion and JWT department scope."""

from pathlib import Path


def test_compiler_has_no_network_or_ai_runtime_imports():
    forbidden = ("httpx", "requests", "aiohttp", "Ollama", "AIGateway")
    findings = []
    for path in Path("backend/app/compiler").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if any(term in content for term in forbidden):
            findings.append(str(path))
    assert findings == []


def test_ingestion_is_markdown_only_and_transactional():
    ingestion = Path("backend/app/services/ingestion.py").read_text(encoding="utf-8")
    route = Path("backend/app/api/v1/knowledge_studio.py").read_text(encoding="utf-8")
    loader = Path("backend/app/compiler/loader.py").read_text(encoding="utf-8")

    assert 'ALLOWED_EXTENSIONS = {".md"}' in ingestion
    assert 'raw_bytes.decode("utf-8-sig")' in route
    assert "department_exists(department_id)" in route
    assert "get_next_version_number(workflow_id)" in route
    assert 'cur.execute("BEGIN")' in loader
    assert 'cur.execute("COMMIT")' in loader
    assert 'rollback_cur.execute("ROLLBACK")' in loader


def test_copilot_request_has_no_department_override():
    model = Path("backend/app/models/copilot.py").read_text(encoding="utf-8")
    request_block = model.split("class CopilotMessageRequest", 1)[1].split(
        "class CopilotResponse", 1
    )[0]

    assert "department" not in request_block
    assert "conversation_id" in request_block
    assert "message" in request_block
