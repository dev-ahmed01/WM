"""Document Loader Sub-Parser Module.

Normalizes markdown source text and automatically detects whether the document is:
  1. Legacy OWD (v1.0 inline directives: ::state[...], ::transition, :::rule)
  2. OWD v1.1 (v1.1 structured sections & blocks)
"""

import re
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("compiler.parser.loader")


class DocumentLoader:
    """Loads raw markdown and detects OWD specification version."""

    @staticmethod
    def load_and_detect(markdown_text: str) -> Tuple[str, str, Dict[str, Any]]:
        """Returns normalized text, detected spec version ('1.0' or '1.1'), and raw sections dictionary."""
        if not markdown_text or not isinstance(markdown_text, str) or not markdown_text.strip():
            return "", "1.0", {}

        normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")

        # Detect OWD v1.1 signatures: presence of YAML frontmatter, # Document Metadata, # AI Retrieval Metadata, or :::metadata
        is_v1_1 = bool(
            re.search(r"^---\s*\n.*?spec_version:\s*['\"]?1\.1", normalized, re.DOTALL | re.IGNORECASE)
            or ":::metadata" in normalized
            or "# Document Metadata" in normalized
            or "# 1 Document Metadata" in normalized
            or ":::ai_retrieval" in normalized
            or "# AI Retrieval Metadata" in normalized
            or "# 2 AI Retrieval Metadata" in normalized
        )

        spec_version = "1.1" if is_v1_1 else "1.0"
        logger.info(f"[DOCUMENT LOADER] Detected OWD specification version: '{spec_version}'")

        # Extract markdown header sections into dictionary
        sections: Dict[str, str] = {}
        current_section = "HEADER"
        current_lines = []

        for line in normalized.splitlines():
            line_trim = line.strip()
            if line_trim.startswith("# "):
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                    current_lines = []
                current_section = line_trim[2:].strip().upper()
            current_lines.append(line)

        if current_lines:
            sections[current_section] = "\n".join(current_lines).strip()

        return normalized, spec_version, sections
