"""Grounded conversational reasoning helpers for the operational Copilot."""

import re
from difflib import SequenceMatcher
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

    @staticmethod
    def _has_navigation_signal(tokens: Sequence[str]) -> bool:
        return any(
            SequenceMatcher(None, token, candidate).ratio() >= 0.75
            for token in tokens
            for candidate in ("next", "then", "further", "now")
        )

    @classmethod
    def classify_move(cls, message: str) -> str:
        normalized = cls._normalized(message)
        tokens = set(normalized.split())
        if "why" in tokens or "reason" in tokens or "purpose" in tokens:
            return "reason"
        if normalized.startswith("what if") or tokens & {
            "broken",
            "cannot",
            "damage",
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
    def last_verified_instruction(
        cls, history: Sequence[Dict[str, Any]]
    ) -> Dict[str, str] | None:
        """Recover the latest grounded instruction and its persisted workflow state."""
        for item in reversed(history):
            if str(item.get("sender") or "").lower() != "ai":
                continue
            instruction = str(item.get("content") or "").strip()
            citations = item.get("citations") or []
            state_id = ""
            for citation in citations if isinstance(citations, list) else []:
                if isinstance(citation, dict) and citation.get("state_id"):
                    state_id = str(citation["state_id"])
                    break
            if not state_id:
                retrieved = item.get("retrieved_state_ids") or []
                if isinstance(retrieved, list) and len(retrieved) == 1:
                    state_id = str(retrieved[0])
            if instruction and state_id:
                return {"instruction": instruction, "state_id": state_id}
        return None

    @classmethod
    def should_reason_about_verified_followup(
        cls, message: str, verified_instruction: str
    ) -> bool:
        """Route likely action follow-ups to semantic classification, not phrase matching."""
        normalized = cls._normalized(message)
        token_list = normalized.split()
        tokens = set(token_list)
        asks_next = cls._has_navigation_signal(token_list)
        if not asks_next:
            return False
        contextual_reference = bool(tokens & {"it", "that", "this", "there"})
        return bool(
            contextual_reference
            or fuzzy_relevance_score(message, verified_instruction) >= 0.20
        )

    @classmethod
    def fallback_verified_followup_plan(
        cls, message: str, verified_instruction: str
    ) -> Dict[str, Any]:
        """Safe grammar-based fallback when the semantic classifier is unavailable."""
        normalized = cls._normalized(message)
        tokens = normalized.split()
        token_set = set(tokens)
        asks_next = cls._has_navigation_signal(tokens)
        negated = bool(token_set & {"not", "never", "cannot", "cant", "havent"})
        instruction_tokens = cls._normalized(verified_instruction).split()
        past_action_match = any(
            token.endswith("ed")
            and any(
                SequenceMatcher(None, token, instruction_token).ratio() >= 0.78
                for instruction_token in instruction_tokens
                if len(instruction_token) >= 4
            )
            for token in tokens
        )
        contextual_past_action = bool(
            token_set & {"it", "that", "this", "there"}
            and any(len(token) >= 4 and token.endswith("ed") for token in tokens)
        )
        generic_attestation = bool(
            token_set & {"complete", "completed", "done", "finished", "performed"}
        )
        completed = asks_next and not negated and (
            past_action_match or contextual_past_action or generic_attestation
        )
        return {
            "relation": "completed" if completed else "unclear",
            "asks_next": asks_next,
            "confidence": 0.76 if completed else 0.0,
            "authoritative": False,
        }

    @classmethod
    def verified_followup_is_actionable(
        cls,
        message: str,
        verified_instruction: str,
        plan: Dict[str, Any],
    ) -> bool:
        """Validate model semantics against the user's words before graph lookup."""
        if (
            str(plan.get("relation")) != "completed"
            or not bool(plan.get("asks_next"))
            or float(plan.get("confidence") or 0.0) < 0.72
        ):
            return False
        tokens = set(cls._normalized(message).split())
        return bool(
            tokens & {"it", "that", "this", "there"}
            or fuzzy_relevance_score(message, verified_instruction) >= 0.20
        )

    @classmethod
    def verified_followup_needs_reminder(
        cls, message: str, plan: Dict[str, Any]
    ) -> bool:
        """Keep incomplete or asking users on the last verified instruction."""
        tokens = set(cls._normalized(message).split())
        explicitly_incomplete = bool(
            tokens & {"not", "never", "cannot", "cant", "havent"}
        )
        semantic_question = bool(
            str(plan.get("relation")) == "asking"
            and float(plan.get("confidence") or 0.0) >= 0.72
        )
        return bool(plan.get("asks_next")) and (explicitly_incomplete or semantic_question)

    @classmethod
    def should_plan_workflow_action(
        cls,
        message: str,
        history: Sequence[Dict[str, Any]],
        current_instruction: str = "",
    ) -> bool:
        """Use the model for ambiguous attestations; explicit controls stay instant.

        This is only a cheap routing gate. It does not decide whether work was
        completed or which outcome applies—that judgment belongs to the structured
        planner and then the deterministic workflow validator.
        """
        if not history or "?" in message:
            return False
        tokens = cls._normalized(message).split()
        if not tokens:
            return False
        completion_vocabulary = (
            "complete",
            "completed",
            "done",
            "finish",
            "finished",
            "performed",
        )
        has_attestation_signal = any(
            any(
                token == candidate
                or len(token) >= 4
                and SequenceMatcher(None, token, candidate).ratio() >= 0.80
                for candidate in completion_vocabulary
            )
            for token in tokens
        )
        has_context_reference = bool(
            set(tokens)
            & {
                "about",
                "all",
                "already",
                "it",
                "previous",
                "prior",
                "task",
                "tasks",
                "that",
                "these",
                "this",
            }
        )
        matches_current_step = bool(
            has_attestation_signal
            and current_instruction
            and fuzzy_relevance_score(message, current_instruction) >= 0.45
        )
        has_contextual_navigation = bool(
            set(tokens) & {"earlier", "previous", "prior"}
            and set(tokens) & {"after", "continue", "further", "next", "step", "steps"}
        )
        return bool(
            has_attestation_signal
            and (has_context_reference or matches_current_step)
            or has_contextual_navigation
        )

    @classmethod
    def workflow_planner_context(
        cls, position: Any, history: Sequence[Dict[str, Any]], history_limit: int
    ) -> tuple[List[Dict[str, str]], Dict[str, Any]]:
        """Expose conversational and current-state context without graph authority."""
        compact_history = cls.compact_history(history, history_limit)
        return compact_history, {
            "current_step_number": position.step_number,
            "current_step_instruction": position.step_title,
            "awaiting_outcome": bool(position.decision_options),
            "allowed_outcome_labels": [
                option.option_label for option in position.decision_options
            ],
        }

    @classmethod
    def fallback_workflow_plan(
        cls, message: str, history: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Resolve discourse generically when the local planner is unavailable.

        This fallback proposes only scope and prior user wording. It supplies no
        workflow fact, and its outcome still requires a unique persisted match.
        """
        normalized = cls._normalized(message)
        tokens = set(normalized.split())
        full_scope = bool(
            tokens & {"all", "each", "every", "everything"}
            or tokens & {"earlier", "previous", "prior"}
            and tokens & {"step", "steps", "task", "tasks"}
        )
        prior_user_topic = cls.previous_operational_topic(history)
        return {
            "intent": "continue_prior_issue" if prior_user_topic else "complete_work",
            "completion_scope": "all_available" if full_scope else "current",
            "outcome_text": (
                cls.focus_operational_query(prior_user_topic)[:300]
                if prior_user_topic
                else ""
            ),
            "needs_clarification": False,
            "confidence": 0.74,
            "authoritative": False,
            "provider": "deterministic_discourse_fallback",
        }

    @classmethod
    def previous_operational_topic(
        cls, history: Sequence[Dict[str, Any]]
    ) -> str:
        """Return the latest operational issue, skipping workflow-control chatter."""
        fallback = ""
        for item in reversed(history):
            if str(item.get("sender") or "").lower() != "employee":
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            normalized = cls._normalized(content)
            tokens = set(normalized.split())
            is_control_chatter = bool(
                tokens & {"earlier", "previous", "prior", "skip"}
                and tokens & {"step", "steps", "task", "tasks"}
                or tokens & {"complete", "completed", "done", "finish", "finished"}
                and tokens & {"step", "steps", "task", "tasks"}
            )
            if is_control_chatter:
                continue
            if cls.classify_move(content) == "exception":
                return content
            fallback = fallback or content
        return fallback

    @classmethod
    def describes_completed_action(
        cls, message: str, source: Dict[str, Any]
    ) -> bool:
        """Identify a user's attestation that they performed the matched step."""
        normalized = cls._normalized(message)
        tokens = set(normalized.split())
        if tokens & {"not", "never", "cannot", "cant", "havent"}:
            return False
        has_completion_language = bool(
            tokens & {"complete", "completed", "done", "finished"}
            or tokens & {"have", "has", "already"}
        )
        if not has_completion_language or "next" not in tokens:
            return False
        sections = cls.evidence_sections(str(source.get("content") or ""))
        instruction = cls._without_code(sections.get("instructions", ""))
        return bool(
            instruction and fuzzy_relevance_score(message, instruction) >= 0.45
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
