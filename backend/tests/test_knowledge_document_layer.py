"""Unit and Integration Tests for Enterprise Knowledge Document Layer.

Validates raw markdown preservation, dynamic frontmatter extraction, structural element parsing,
AI metadata computation, chunk object creation, lineage audit trails, and DocumentRepository lookups.
"""

from app.compiler.parsers.metadata_parser import MetadataParser
from app.compiler.parsers.ast_builder import ASTBuilder
from app.compiler.compiler import OWDCompiler
from app.repositories.document_repository import DocumentRepository

SAMPLE_OWD_MARKDOWN = """---
author: "Alice Smith"
reviewer: "Bob Jones"
facility: "Warehouse-01"
risk_level: "HIGH"
tags:
  - "inbound"
  - "logistics"
---

# SOP-RCV-001: Receive Inbound Shipment

:::metadata
sop_id: SOP-RCV-001
version: 1.1.0
department: dept_logistics
category: OPERATIONAL_SOP
owner: Logistics Manager
:::

## Workflow Definition
- Objective: Safely receive inbound freight shipments.
- Business Goal: Zero damage and 100% manifest accuracy.

## State 1: Dock Arrival (state_dock_arrival)
- Step 1: Verify carrier bill of lading against purchase order manifest.
- Step 2: Perform visual inspection of trailer seal.

| Checklist Item | Required Status |
| Seal Intact | PASS |
| Temp Logged | PASS |

```python
def verify_seal(seal_code):
    return seal_code.startswith("SEAL-")
```

![Dock Door](/images/dock.png)
[Safety SOP](file:///docs/safety.md)
"""


def test_frontmatter_and_element_extraction():
    raw_yaml, fm_dict = MetadataParser.extract_frontmatter_dict(SAMPLE_OWD_MARKDOWN)
    assert raw_yaml is not None
    assert fm_dict["author"] == "Alice Smith"
    assert fm_dict["facility"] == "Warehouse-01"
    assert "inbound" in fm_dict["tags"]

    elements = MetadataParser.extract_document_elements(SAMPLE_OWD_MARKDOWN)
    assert len(elements["sections"]) >= 3
    assert len(elements["tables"]) == 1
    assert elements["tables"][0]["headers"] == ["Checklist Item", "Required Status"]
    assert len(elements["code_blocks"]) == 1
    assert elements["code_blocks"][0]["language"] == "python"
    assert len(elements["images"]) == 1
    assert len(elements["links"]) == 1


def test_ast_builder_preserves_raw_markdown_and_elements():
    ast = ASTBuilder.build_ast(SAMPLE_OWD_MARKDOWN, workflow_code="SOP-RCV-001")
    assert ast.raw_markdown == SAMPLE_OWD_MARKDOWN
    assert ast.frontmatter["author"] == "Alice Smith"
    assert len(ast.tables) == 1
    assert len(ast.code_blocks) == 1


def test_compiler_generates_enterprise_payloads():
    ast = ASTBuilder.build_ast(SAMPLE_OWD_MARKDOWN, workflow_code="SOP-RCV-001")
    compiled = OWDCompiler.compile(
        ast,
        stage_file_uri="@RAW_OWD_STAGE/SOP-RCV-001/v1/hash/receive.md",
        source_filename="receive.md",
    )

    assert len(compiled.documents_payload) == 1
    doc = compiled.documents_payload[0]
    assert doc["document_name"] == "Receive Inbound Shipment"
    assert doc["author"] == "Alice Smith"
    assert doc["original_filename"] == "receive.md"

    assert len(compiled.contents_payload) == 1
    cont = compiled.contents_payload[0]
    assert cont["raw_markdown"] == SAMPLE_OWD_MARKDOWN
    assert len(cont["tables_json"]) == 1

    assert len(compiled.ai_metadata_payload) == 1
    ai = compiled.ai_metadata_payload[0]
    assert ai["word_count"] > 10
    assert ai["embedding_model"] == "none"
    assert ai["embedding_status"] == "NOT_REQUIRED"
    assert ai["evaluation_score"] is None

    assert len(compiled.chunks_payload) >= 1
    chunk = compiled.chunks_payload[0]
    assert chunk["chunk_type"] == "STATE_STEP"
    assert chunk["character_count"] > 0

    assert len(compiled.lineage_payload) == 1
    lin = compiled.lineage_payload[0]
    assert lin["parser_name"] == "OWDParser"
    assert lin["status"] == "PUBLISHED"


def test_document_repository_returns_empty_results_without_faking_data(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []

    @contextmanager
    def connection():
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        yield conn

    monkeypatch.setattr("app.repositories.document_repository.get_snowflake_connection", connection)
    assert DocumentRepository.get_document_by_id("doc_non_existent") is None
    assert DocumentRepository.get_document_content("doc_non_existent") is None
    assert DocumentRepository.get_document_chunks("doc_non_existent") == []
    assert DocumentRepository.get_document_lineage("doc_non_existent") == []
