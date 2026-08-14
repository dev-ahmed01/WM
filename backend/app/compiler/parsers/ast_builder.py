"""AST Builder Orchestration Module.

Wires DocumentLoader and all 11 section sub-parsers to assemble a single,
validated UnifiedAST object representing the complete SOP.
"""

import logging
import re

from app.compiler.models import UnifiedAST, Workflow
from app.compiler.parsers.document_loader import DocumentLoader
from app.compiler.parsers.metadata_parser import MetadataParser
from app.compiler.parsers.retrieval_metadata_parser import RetrievalMetadataParser
from app.compiler.parsers.workflow_definition_parser import WorkflowDefinitionParser
from app.compiler.parsers.state_parser import StateParser
from app.compiler.parsers.user_context_parser import UserContextParser
from app.compiler.parsers.analytics_parser import AnalyticsParser
from app.compiler.parsers.relationship_parser import RelationshipParser
from app.compiler.parsers.reference_parser import ReferenceParser
from app.compiler.parsers.json_table_adapter import JsonTableOWDAdapter
from app.compiler.utils import calculate_source_hash, sanitize_code

logger = logging.getLogger("compiler.parser.ast_builder")


class ASTBuilder:
    """Orchestrates modular sub-parsers to build a UnifiedAST object graph."""

    @staticmethod
    def build_ast(
        markdown_text: str,
        workflow_code: str = "",
        title: str = "",
        department_id: str = "",
        category: str = "OPERATIONAL_SOP",
        default_version: int = 1,
    ) -> UnifiedAST:
        """Runs DocumentLoader -> Sub-Parsers -> UnifiedAST pipeline."""
        adapted_markdown = JsonTableOWDAdapter.adapt(markdown_text, department_id=department_id)
        normalized, spec_version, sections = DocumentLoader.load_and_detect(adapted_markdown)
        raw_hash = calculate_source_hash(markdown_text)

        # 1. Section 1: Document Metadata
        metadata = MetadataParser.parse(normalized, default_code=workflow_code)

        doc_code = sanitize_code(workflow_code or metadata.sop_id, prefix="")
        dept_id = department_id or metadata.department or "dept_operations"
        cat = category or metadata.category or "OPERATIONAL_SOP"

        # 2. Section 2: AI Retrieval Metadata
        retrieval_metadata = RetrievalMetadataParser.parse(normalized)

        # 3. Section 3: Workflow Definition
        workflow_def = WorkflowDefinitionParser.parse(normalized, default_title=title or doc_code)

        # Parse the document into a list of AST nodes to feed the structural parsers
        from app.compiler.parsers.document_parser import DocumentParser
        ast_nodes = DocumentParser.parse_to_ast(normalized)

        # 4. Section 4 & 5 & 7: States, Steps, Decisions
        states = StateParser.parse_states(ast_nodes)
        
        # Set ordinal indices globally to prevent flattened ordering
        global_step_idx = 1
        for s_idx, s in enumerate(states, start=1):
            s.ordinal_index = s_idx
            for st in s.steps:
                st.ordinal_index = global_step_idx
                global_step_idx += 1

        # 5. Section 8: User Context
        user_context = UserContextParser.parse(normalized, default_dept=dept_id)

        # 6. Section 9: Analytics Metadata
        analytics = AnalyticsParser.parse(normalized)

        # 7. Section 10: Relationships
        relationships = RelationshipParser.parse(normalized)

        # 8. Section 11: References
        references = ReferenceParser.parse(normalized)

        # Assemble Root Workflow entity
        wf_title = title or metadata.sop_id.replace("_", " ").title()
        for line in normalized.splitlines():
            line_trim = line.strip()
            if line_trim.startswith("# ") and not title:
                header_text = line_trim[2:].strip()
                if re.match(r"^\d+\s+", header_text) or "document metadata" in header_text.lower():
                    continue
                if ":" in header_text:
                    parts = header_text.split(":", 1)
                    wf_title = parts[1].strip()
                else:
                    wf_title = header_text
                break

        workflow_entity = Workflow(
            workflow_code=doc_code,
            title=wf_title,
            department_id=dept_id,
            category=cat,
            description=workflow_def.workflow_objective or f"OWD workflow for {wf_title}",
            version_number=default_version,
            states=states,
        )

        # Extract raw YAML frontmatter & markdown elements for enterprise document layer
        fm_yaml, fm_dict = MetadataParser.extract_frontmatter_dict(markdown_text)
        doc_elements = MetadataParser.extract_document_elements(normalized)

        unified_ast = UnifiedAST(
            spec_version=spec_version,
            workflow=workflow_entity,
            metadata=metadata,
            retrieval_metadata=retrieval_metadata,
            workflow_definition=workflow_def,
            user_context=user_context,
            analytics=analytics,
            relationships=relationships,
            v1_1_references=references,
            raw_source_hash=raw_hash,
            parsed_metadata={
                "spec_version": spec_version,
                "sections_count": len(sections),
                "states_count": len(states),
            },
            raw_markdown=markdown_text,
            frontmatter_yaml=fm_yaml,
            frontmatter=fm_dict,
            sections=doc_elements.get("sections", []),
            tables=doc_elements.get("tables", []),
            code_blocks=doc_elements.get("code_blocks", []),
            images=doc_elements.get("images", []),
            links=doc_elements.get("links", []),
        )

        # 9. Run Validation Engine
        from app.compiler.validation_engine import ValidationEngine
        unified_ast = ValidationEngine.validate_and_enrich(unified_ast)

        logger.info(f"[AST BUILDER SUCCESS] Assembled UnifiedAST (v{spec_version}) for '{doc_code}': {len(states)} states.")
        return unified_ast
