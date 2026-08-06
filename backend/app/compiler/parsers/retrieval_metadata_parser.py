"""Retrieval Metadata Parser Sub-Parser Module (Section 2).

Parses AI Retrieval Metadata:
  Keywords, Synonyms, Search Phrases, Search Queries, Business Process,
  Equipment, Workflow Tags, Embedding Metadata, Vector Metadata, Cortex Search Metadata.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import AIRetrievalMetadata

logger = logging.getLogger("compiler.parser.retrieval")


class RetrievalMetadataParser:
    """Parses Section 2: AI Retrieval Metadata."""

    @staticmethod
    def parse(markdown_text: str) -> AIRetrievalMetadata:
        """Parses Section 2 AI retrieval metadata."""
        ret_dict: Dict[str, Any] = {}

        # 1. Check :::retrieval_metadata directive block
        directive_match = re.search(r":::retrieval_metadata\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    ret_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::retrieval_metadata block: {exc}")

        # 2. Check '# AI Retrieval Metadata' section
        sec_match = re.search(r"#\s*(?:2\s*)?AI Retrieval Metadata\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    k_clean = k.strip().lower().replace(" ", "_")
                    v_clean = v.strip().strip('"\'')
                    if k_clean not in ret_dict or not ret_dict[k_clean]:
                        ret_dict[k_clean] = v_clean

        def parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.split(",") if x.strip()]
            return []

        return AIRetrievalMetadata(
            keywords=parse_list(ret_dict.get("keywords")),
            synonyms=parse_list(ret_dict.get("synonyms")),
            search_phrases=parse_list(ret_dict.get("search_phrases")),
            search_queries=parse_list(ret_dict.get("search_queries")),
            business_process=str(ret_dict.get("business_process", "Operational Workflow")),
            equipment=parse_list(ret_dict.get("equipment")),
            workflow_tags=parse_list(ret_dict.get("workflow_tags")),
            embedding_metadata=ret_dict.get("embedding_metadata", {}),
            vector_metadata=ret_dict.get("vector_metadata", {}),
            cortex_search_metadata=ret_dict.get("cortex_search_metadata", {}),
        )
