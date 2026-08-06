"""Knowledge Relationship Parser Sub-Parser Module (Section 10).

Parses Knowledge Graph Edges:
  Parent SOP, Child SOPs, Related SOPs, Previous SOP, Next SOP,
  Escalation SOP, Exception SOP, Referenced Equipment, Referenced Documents, Referenced Policies.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import KnowledgeRelationship

logger = logging.getLogger("compiler.parser.relationship")


class RelationshipParser:
    """Parses Section 10: Knowledge Relationships."""

    @staticmethod
    def parse(markdown_text: str) -> List[KnowledgeRelationship]:
        """Parses Section 10 knowledge relationships."""
        rel_dict: Dict[str, Any] = {}

        # 1. Check :::relationships block
        directive_match = re.search(r":::relationships\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    rel_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::relationships block: {exc}")

        # 2. Check '# Knowledge Relationships' section
        sec_match = re.search(r"#\s*(?:10\s*)?Knowledge Relationships\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    rel_dict[k.strip().lower().replace(" ", "_")] = v.strip().strip('"\'')

        relationships: List[KnowledgeRelationship] = []

        type_mapping = {
            "parent_sop": "PARENT_SOP",
            "child_sops": "CHILD_SOP",
            "related_sops": "RELATED_SOP",
            "previous_sop": "PREVIOUS_SOP",
            "next_sop": "NEXT_SOP",
            "escalation_sop": "ESCALATION_SOP",
            "exception_sop": "EXCEPTION_SOP",
            "referenced_equipment": "REFERENCED_EQUIPMENT",
            "referenced_documents": "REFERENCED_DOCUMENT",
            "referenced_policies": "REFERENCED_POLICY",
        }

        for key, rel_type in type_mapping.items():
            if key in rel_dict and rel_dict[key]:
                val = rel_dict[key]
                items = val if isinstance(val, list) else [x.strip() for x in str(val).split(",") if x.strip()]
                for target in items:
                    relationships.append(
                        KnowledgeRelationship(
                            relationship_type=rel_type,
                            target_reference=str(target),
                            description=f"Graph edge: {rel_type} -> {target}",
                        )
                    )

        return relationships
