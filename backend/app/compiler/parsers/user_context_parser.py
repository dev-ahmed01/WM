"""User Context & Permissions Parser Sub-Parser Module (Section 8).

Parses User Context & RBAC Permissions:
  Roles, Permissions, Experience Levels, Certifications,
  Supported Languages, Department.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from app.compiler.models import UserContextPermissions

logger = logging.getLogger("compiler.parser.user_context")


class UserContextParser:
    """Parses Section 8: User Context & Permissions."""

    @staticmethod
    def parse(markdown_text: str, default_dept: str = "dept_operations") -> UserContextPermissions:
        """Parses Section 8 user context and permissions."""
        uc_dict: Dict[str, Any] = {}

        # 1. Check :::user_context block
        directive_match = re.search(r":::user_context\s*\n(.*?)\n:::", markdown_text, re.DOTALL | re.IGNORECASE)
        if directive_match:
            try:
                parsed_yaml = yaml.safe_load(directive_match.group(1))
                if isinstance(parsed_yaml, dict):
                    uc_dict.update(parsed_yaml)
            except Exception as exc:
                logger.warning(f"Failed to parse :::user_context block: {exc}")

        # 2. Check '# User Context' section
        sec_match = re.search(r"#\s*(?:8\s*)?User Context\s*\n(.*?)(?=\n#|\Z)", markdown_text, re.DOTALL | re.IGNORECASE)
        if sec_match:
            for line in sec_match.group(1).splitlines():
                line_trim = line.strip().lstrip("-* ").strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    k_clean = k.strip().lower().replace(" ", "_")
                    v_clean = v.strip().strip('"\'')
                    if k_clean not in uc_dict or not uc_dict[k_clean]:
                        uc_dict[k_clean] = v_clean

        def parse_list(val: Any, default: List[str]) -> List[str]:
            if isinstance(val, list):
                res = [str(x).strip() for x in val if str(x).strip()]
                return res if res else default
            if isinstance(val, str) and val.strip():
                res = [x.strip() for x in val.split(",") if x.strip()]
                return res if res else default
            return default

        return UserContextPermissions(
            roles=parse_list(uc_dict.get("roles"), ["Employee", "Supervisor", "Admin"]),
            permissions=parse_list(uc_dict.get("permissions"), ["knowledge.read", "workflow.execute"]),
            experience_levels=parse_list(uc_dict.get("experience_levels"), ["JUNIOR", "INTERMEDIATE", "SENIOR"]),
            certifications=parse_list(uc_dict.get("certifications"), ["FORKLIFT_CERTIFIED", "SAFETY_LEVEL_1"]),
            supported_languages=parse_list(uc_dict.get("supported_languages"), ["en-US"]),
            department=str(uc_dict.get("department", default_dept)),
        )
