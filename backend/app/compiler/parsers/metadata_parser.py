"""Metadata Parser Sub-Parser Module (Section 1).

Parses Document Metadata from markdown blocks or YAML frontmatter:
  SOP ID, Version, Department, Category, Owner, Priority, Difficulty,
  Estimated Duration, Roles Allowed, Required Equipment, Dependencies,
  Related SOPs, Review Cycle, Effective Date.
"""

import re
import yaml
import logging
from typing import Dict, Any, List, Optional
from app.compiler.models import DocumentMetadata
from app.compiler.utils import sanitize_code

logger = logging.getLogger("compiler.parser.metadata")


class MetadataParser:
    """Parses Section 1: Document Metadata."""

    @staticmethod
    def parse(markdown_text: str, default_code: str = "") -> DocumentMetadata:
        """Parses Section 1 document metadata."""
        meta_dict: Dict[str, Any] = {}

        # 1. Check YAML frontmatter at top of document
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown_text, re.DOTALL)
        if frontmatter_match:
            try:
                parsed_yaml = yaml.safe_load(frontmatter_match.group(1))
                if isinstance(parsed_yaml, dict):
                    meta_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse YAML frontmatter: {exc}")

        # 2. Check :::metadata directive block
        directive_match = re.search(r":::metadata\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            for line in directive_match.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta_dict[k.strip().lower()] = v.strip().strip('"\'')

        # 3. Check '# Document Metadata' header section
        sec_match = re.search(r"#\s*(?:1\s*)?Document Metadata\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    k_clean = k.strip().lower().replace(" ", "_")
                    v_clean = v.strip().strip('"\'')
                    if k_clean not in meta_dict or not meta_dict[k_clean]:
                        meta_dict[k_clean] = v_clean

        # 4. Check top markdown title header: # SOP-XYZ: Title
        for line in markdown_text.splitlines():
            line_trim = line.strip()
            if line_trim.startswith("# "):
                header_text = line_trim[2:].strip()
                if ":" in header_text:
                    parts = header_text.split(":", 1)
                    cand = parts[0].strip()
                    if cand.upper() == "SOP":
                        cand = f"SOP-{parts[1].split()[0]}"
                    if cand.upper().startswith("SOP") or "-" in cand or "_" in cand:
                        if "sop_id" not in meta_dict or not meta_dict["sop_id"]:
                            meta_dict["sop_id"] = cand
                        break
                elif re.match(r"^\d+\s+", header_text):
                    continue  # Skip numbered headers like '# 1 Document Metadata'
                else:
                    break

        # Fallbacks for SOP ID and defaults
        sop_id_raw = (
            meta_dict.get("workflow_code")
            or meta_dict.get("sop_id")
            or meta_dict.get("sop_code")
            or meta_dict.get("id")
            or default_code
            or "SOP-DOC-001"
        )
        sop_id = sanitize_code(sop_id_raw, prefix="")

        def parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.split(",") if x.strip()]
            return []

        return DocumentMetadata(
            sop_id=sop_id,
            version=str(meta_dict.get("version", "1.1.0")),
            department=str(meta_dict.get("department", "dept_operations")),
            category=str(meta_dict.get("category", "OPERATIONAL_SOP")),
            owner=str(meta_dict.get("owner", "System Admin")),
            priority=str(meta_dict.get("priority", "MEDIUM")).upper(),
            difficulty=str(meta_dict.get("difficulty", "INTERMEDIATE")).upper(),
            estimated_duration=str(meta_dict.get("estimated_duration", "30 mins")),
            roles_allowed=parse_list(meta_dict.get("roles_allowed")) or ["Employee", "Supervisor", "Admin"],
            required_equipment=parse_list(meta_dict.get("required_equipment")),
            dependencies=parse_list(meta_dict.get("dependencies")),
            related_sops=parse_list(meta_dict.get("related_sops")),
            review_cycle=str(meta_dict.get("review_cycle", "ANNUAL")),
            effective_date=str(meta_dict.get("effective_date", "2026-01-01")),
        )

    @staticmethod
    def extract_frontmatter_dict(markdown_text: str) -> tuple[Optional[str], Dict[str, Any]]:
        """Extracts complete raw YAML frontmatter string and dynamic dictionary."""
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", markdown_text, re.DOTALL)
        if not frontmatter_match:
            return None, {}
        yaml_raw = frontmatter_match.group(1)
        try:
            parsed = yaml.safe_load(yaml_raw)
            if isinstance(parsed, dict):
                return yaml_raw, parsed
        except Exception as exc:
            logger.warning(f"Error parsing raw YAML frontmatter: {exc}")
        return yaml_raw, {}

    @staticmethod
    def extract_document_elements(markdown_text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Extracts markdown structural elements: sections, tables, code blocks, images, links."""
        sections: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        code_blocks: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []

        # 1. Sections (#, ##, ###)
        for sec in re.finditer(r"^(#{1,6})\s+(.+)$", markdown_text, re.MULTILINE):
            sections.append({
                "level": len(sec.group(1)),
                "title": sec.group(2).strip(),
            })

        # 2. Code blocks (```lang ... ```)
        for cb in re.finditer(r"```(\w*)\n(.*?)```", markdown_text, re.DOTALL):
            code_blocks.append({
                "language": cb.group(1) or "plain",
                "code": cb.group(2).strip(),
                "char_length": len(cb.group(2).strip()),
            })

        # 3. Tables (| col | col |)
        table_lines: List[str] = []
        in_table = False
        table_count = 0
        for line in markdown_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("|") and line_str.endswith("|"):
                table_lines.append(line_str)
                in_table = True
            elif in_table:
                if len(table_lines) >= 2:
                    table_count += 1
                    headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]
                    rows = [[c.strip() for c in r.split("|")[1:-1]] for r in table_lines[1:] if not re.match(r"^\|[-:\s|]+\|$", r)]
                    tables.append({
                        "table_index": table_count,
                        "headers": headers,
                        "row_count": len(rows),
                        "rows": rows,
                    })
                table_lines = []
                in_table = False
        if in_table and len(table_lines) >= 2:
            table_count += 1
            headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]
            rows = [[c.strip() for c in r.split("|")[1:-1]] for r in table_lines[1:] if not re.match(r"^\|[-:\s|]+\|$", r)]
            tables.append({
                "table_index": table_count,
                "headers": headers,
                "row_count": len(rows),
                "rows": rows,
            })

        # 4. Images (![alt](url))
        for img in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown_text):
            images.append({
                "alt_text": img.group(1),
                "url": img.group(2),
            })

        # 5. Links ([label](url))
        for link in re.finditer(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)", markdown_text):
            links.append({
                "label": link.group(1),
                "url": link.group(2),
            })

        return {
            "sections": sections,
            "tables": tables,
            "code_blocks": code_blocks,
            "images": images,
            "links": links,
        }
