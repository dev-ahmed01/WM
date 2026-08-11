"""Grounded conversational reasoning helpers for the operational Copilot."""

import re
from typing import Any, Dict, List, Sequence

from app.core.text_matching import fuzzy_relevance_score


class CopilotReasoningService:
    """Resolve conversational intent without granting the model workflow authority."""

    _FOLLOW_UPS = {
        "and then",
        "how so",
        "then what",
        "what about that",
        "what happens then",
        "what next",
        "why",
    }

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (text or "").casefold()))

    @classmethod
    def classify_move(cls, message: str) -> str:
        normalized = cls._normalized(message)
        tokens = set(normalized.split())
        if "why" in tokens or "reason" in tokens or "purpose" in tokens:
            return "reason"
        if normalized.startswith("what if") or tokens & {
            "broken",
            "cannot",
            "damaged",
            "error",
            "fails",
            "failure",
            "mismatch",
            "missing",
            "wrong",
        }:
            return "exception"
        if tokens & {"explain", "clarify", "mean"}:
            return "explain"
        if "next" in tokens or normalized in {"and then", "then what"}:
            return "next"
        if "how" in tokens:
            return "procedure"
        return "question"

    @classmethod
    def is_contextual_follow_up(cls, message: str) -> bool:
        normalized = cls._normalized(message)
        tokens = normalized.split()
        return (
            normalized in cls._FOLLOW_UPS
            or len(tokens) <= 3
            and bool(set(tokens) & {"it", "that", "then", "this", "why"})
        )

    @classmethod
    def resolve_query(
        cls, message: str, history: Sequence[Dict[str, Any]]
    ) -> str:
        """Attach the last employee topic to an otherwise ambiguous follow-up."""
        if not cls.is_contextual_follow_up(message):
            return message.strip()
        previous_user_message = next(
            (
                str(item.get("content") or "").strip()
                for item in reversed(history)
                if str(item.get("sender") or "").lower() == "employee"
                and str(item.get("content") or "").strip()
            ),
            "",
        )
        return (
            f"{previous_user_message} Follow-up: {message.strip()}"
            if previous_user_message
            else message.strip()
        )

    @classmethod
    def focus_operational_query(cls, message: str) -> str:
        """Drop conversational lead-in before a clear exception/topic anchor."""
        if cls.classify_move(message) != "exception":
            return message.strip()
        tokens = re.findall(r"[a-z0-9_-]+", (message or "").casefold())
        anchors = {
            "box",
            "boxes",
            "broken",
            "carton",
            "cartons",
            "container",
            "containers",
            "damage",
            "damaged",
            "error",
            "failed",
            "failure",
            "mismatch",
            "missing",
            "package",
            "packages",
            "pallet",
            "pallets",
            "seal",
            "temperature",
            "thermometer",
            "wrong",
        }
        first_anchor = next(
            (index for index, token in enumerate(tokens) if token in anchors), None
        )
        if first_anchor is None:
            return message.strip()
        focused = " ".join(tokens[first_anchor:]).strip()
        return focused or message.strip()

    @staticmethod
    def compact_history(
        history: Sequence[Dict[str, Any]], limit: int
    ) -> List[Dict[str, str]]:
        compact: List[Dict[str, str]] = []
        for item in history[-max(0, limit) :]:
            sender = str(item.get("sender") or "").lower()
            content = str(item.get("content") or "").strip()
            if sender not in {"employee", "ai"} or not content:
                continue
            compact.append(
                {
                    "role": "user" if sender == "employee" else "assistant",
                    "content": content[:600],
                }
            )
        return compact

    @staticmethod
    def evidence_sections(content: str) -> Dict[str, str]:
        sections: Dict[str, str] = {}
        for part in str(content or "").split(" | "):
            if ":" not in part:
                continue
            label, value = part.split(":", 1)
            sections[label.strip().casefold()] = value.strip()
        return sections

    @staticmethod
    def _without_code(value: str) -> str:
        return re.sub(r"^(?:STEP|RULE)_[A-Z0-9_-]+\s+", "", value or "").strip()

    @classmethod
    def active_step_answer(
        cls,
        query: str,
        move: str,
        position: Any,
        source: Dict[str, Any],
    ) -> str | None:
        """Explain a current step or hard stop using only persisted source fields."""
        sections = cls.evidence_sections(str(source.get("content") or ""))
        instruction = cls._without_code(sections.get("instructions", ""))
        rule = cls._without_code(sections.get("rules", ""))
        current_instruction = instruction or str(position.step_title or "").strip()
        active_context = " ".join(
            part
            for part in (
                str(position.state_title or "").strip(),
                current_instruction,
                rule,
            )
            if part
        )
        if (
            move == "reason"
            and rule
            and fuzzy_relevance_score(query, active_context) >= 0.35
        ):
            return f"{rule} Current step remains: {current_instruction}"
        if (
            move == "exception"
            and rule
            and fuzzy_relevance_score(query, rule) >= 0.45
        ):
            return f"{rule} Current step remains: {current_instruction}"
        if move == "explain" and rule:
            return f"Current step: {current_instruction} Relevant rule: {rule}"
        return None

    @classmethod
    def concise_extract(cls, question: str, source: Dict[str, Any]) -> str:
        """Return a readable verified fact instead of serialized retrieval metadata."""
        sections = cls.evidence_sections(str(source.get("content") or ""))
        instruction = cls._without_code(sections.get("instructions", ""))
        rule = cls._without_code(sections.get("rules", ""))
        move = cls.classify_move(question)
        if rule and (
            move == "reason"
            or move == "exception"
            and fuzzy_relevance_score(question, rule) >= 0.45
        ):
            return rule
        if instruction:
            return instruction
        if rule:
            return rule
        state = sections.get("state") or str(source.get("step_title") or "").strip()
        if state:
            return state
        return str(source.get("content") or "").strip()[:500]

    @classmethod
    def agent_context(
        cls,
        move: str,
        history: Sequence[Dict[str, Any]],
        position: Any | None,
        role: str,
        department_id: str,
        history_limit: int,
    ) -> Dict[str, Any]:
        workflow_context: Dict[str, Any] | None = None
        if position is not None:
            workflow_context = {
                "state_id": position.state_id,
                "state_title": position.state_title,
                "state_type": position.state_type,
                "current_step_number": position.step_number,
                "current_step_instruction": position.step_title,
                "decision_options": [
                    {
                        "option_code": option.option_code,
                        "option_label": option.option_label,
                    }
                    for option in position.decision_options
                ],
            }
        return {
            "conversation_move": move,
            "conversation_history": cls.compact_history(history, history_limit),
            "workflow_context": workflow_context,
            "caller_context": {"role": role, "department_id": department_id},
        }
