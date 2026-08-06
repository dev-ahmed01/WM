"""Reference Parser Sub-Parser Module (Section 11).

Parses Reference Citations & Standards:
  Primary Source, Supporting Sources, Official Documentation URL,
  Compliance Standards, Documentation Sections.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import ReferenceV1_1

logger = logging.getLogger("compiler.parser.reference")


class ReferenceParser:
    """Parses Section 11: References."""

    @staticmethod
    def parse(markdown_text: str) -> List[ReferenceV1_1]:
        """Parses Section 11 references."""
        ref_dict: Dict[str, Any] = {}

        # 1. Check :::references block
        directive_match = re.search(r":::references\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    ref_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::references block: {exc}")

        # 2. Check '# References' section
        sec_match = re.search(r"#\s*(?:11\s*)?References\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    ref_dict[k.strip().lower().replace(" ", "_")] = v.strip().strip('"\'')

        references: List[ReferenceV1_1] = []

        type_mapping = {
            "primary_source": "PRIMARY_SOURCE",
            "supporting_sources": "SUPPORTING_SOURCE",
            "official_documentation_url": "OFFICIAL_URL",
            "compliance_standards": "COMPLIANCE_STANDARD",
            "documentation_sections": "DOC_SECTION",
        }

        for key, ref_type in type_mapping.items():
            if key in ref_dict and ref_dict[key]:
                val = ref_dict[key]
                items = val if isinstance(val, list) else [x.strip() for x in str(val).split(",") if x.strip()]
                for target in items:
                    references.append(
                        ReferenceV1_1(
                            reference_type=ref_type,
                            title=f"{ref_type.title().replace('_', ' ')} Reference",
                            citation_uri=str(target),
                        )
                    )

        # Fallback if no explicit references block
        if not references:
            references.append(
                ReferenceV1_1(
                    reference_type="PRIMARY_SOURCE",
                    title="Enterprise Standard Operating Guidelines",
                    citation_uri="https://docs.workmate.ai/sops/guidelines",
                )
            )

        return references
