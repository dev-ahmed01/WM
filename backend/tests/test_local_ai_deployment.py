"""Static deployment contract tests for the self-hosted AI runtime."""

from pathlib import Path


def test_compose_starts_ollama_without_profile_and_uses_service_hostname():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "profiles:" not in compose
    assert "LOCAL_AI_BASE_URL: http://ollama:11434" in compose
    assert "condition: service_healthy" in compose
    assert "condition: service_completed_successfully" in compose
    assert 'ollama_data:/root/.ollama' in compose


def test_compose_initializes_both_configurable_models():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "ollama-model-init:" in compose
    assert "${LOCAL_CHAT_MODEL:-qwen2.5:3b}" in compose
    assert "${LOCAL_EMBEDDING_MODEL:-nomic-embed-text}" in compose


def test_no_managed_ai_runtime_or_migration_remnants():
    migration_names = sorted(path.name for path in Path("analytics/migrations").glob("*.sql"))
    assert migration_names == [
        "01_schemas.sql", "02_security.sql", "03_knowledge_studio.sql",
        "04_workmate_copilot.sql", "05_intelligence_hub.sql", "06_shared.sql",
        "08_seed_data.sql", "09_owd_v1_1_tables.sql",
        "10_enterprise_document_layer.sql", "12_runtime_alignment.sql",
        "13_runtime_prerequisites.sql", "14_runtime_integrity.sql",
        "15_active_workflow_versions.sql", "16_flexible_owd_authoring_metadata.sql",
        "17_multilingual_voice.sql",
    ]
    assert all("search_service" not in name for name in migration_names)

    forbidden = (
        "CORTEX",
        "AI_COMPLETE",
        "SEARCH_PREVIEW",
        "SNOWFLAKE.CORTEX",
        "CORTEX_SEARCH",
        "CORTEX_COMPLETE",
    )
    executable_roots = (
        Path("backend"),
        Path("analytics"),
        Path("scripts"),
        Path("infra"),
        Path("automation"),
        Path("ai-services"),
    )
    findings = []
    this_test = Path(__file__).resolve()
    for root in executable_roots:
        for path in root.rglob("*"):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.resolve() == this_test
            ):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").upper()
            if any(term in content for term in forbidden):
                findings.append(str(path))
    assert findings == []
