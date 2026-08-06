"""AI Conversation Layer Sub-Parser Module (Section 6).

Parses interactive step AI Conversation Layer prompts:
  Question AI Should Ask, Expected User Responses, Clarification Questions,
  Fallback Prompt, Coaching Prompt, Escalation Trigger, Confidence Requirements, Citation Source.
"""

import re
import yaml
import logging
from typing import Dict, Any, List, Optional
from app.compiler.models import AIConversationLayer

logger = logging.getLogger("compiler.parser.ai_conversation")


class AIConversationParser:
    """Parses Section 6: AI Conversation Layer."""

    @staticmethod
    def parse_block(block_text: str, default_instruction: str = "") -> Optional[AIConversationLayer]:
        """Parses an AI conversation block or directive."""
        if ":::ai_conversation" not in block_text.lower() and "question_ai_should_ask" not in block_text.lower():
            return None
            
        conv_dict: Dict[str, Any] = {}

        # 1. Parse :::ai_conversation directive block or section
        directive_match = re.search(r":::ai_conversation\s*\n(.*?)(?=\n:::|\Z)", block_text, re.DOTALL | re.IGNORECASE)
        target_text = directive_match.group(1) if directive_match else block_text

        if "question_ai_should_ask" in target_text or ":::ai_conversation" in block_text:
            try:
                parsed_yaml = yaml.safe_load(target_text)
                if isinstance(parsed_yaml, dict):
                    conv_dict.update(parsed_yaml)
            except Exception:
                pass

            for line in target_text.splitlines():
                line_trim = line.strip()
                if ":" in line_trim:
                    k, v = line_trim.split(":", 1)
                    k_clean = k.strip().lower().replace(" ", "_")
                    v_clean = v.strip().strip('"\'')
                    if k_clean not in conv_dict or not conv_dict[k_clean]:
                        conv_dict[k_clean] = v_clean

        def parse_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.split(",") if x.strip()]
            return []

        q_ask = str(conv_dict.get("question_ai_should_ask") or conv_dict.get("question") or f"Have you completed step: {default_instruction}?")

        return AIConversationLayer(
            question_ai_should_ask=q_ask,
            expected_user_responses=parse_list(conv_dict.get("expected_user_responses", ["Yes", "No", "Complete"])),
            clarification_questions=parse_list(conv_dict.get("clarification_questions")),
            fallback_prompt=conv_dict.get("fallback_prompt", "Please clarify your entry."),
            coaching_prompt=conv_dict.get("coaching_prompt", "Refer to standard operating guidelines."),
            escalation_trigger=conv_dict.get("escalation_trigger", "MAX_RETRIES_EXCEEDED"),
            confidence_requirements=str(conv_dict.get("confidence_requirements", "0.85")),
            citation_source=conv_dict.get("citation_source", "SOP_STANDARD_DOC"),
        )
