"""Deterministic workflow-selection and execution-intent resolution."""

import re
from typing import Any, Dict, Sequence

from app.core.text_matching import fuzzy_relevance_score, search_terms


class WorkflowIntentService:
    """Resolve obvious workflow intents without depending on an LLM or embeddings."""

    _WORKFLOW_REQUEST_WORDS = {
        "fetch",
        "find",
        "get",
        "give",
        "launch",
        "load",
        "navigate",
        "need",
        "open",
        "procedure",
        "process",
        "show",
        "sop",
        "start",
        "take",
        "want",
        "workflow",
    }
    _CONFIRMATION_WORDS = {"yes", "yeah", "yep", "correct", "confirm", "start", "proceed"}
    _REJECTION_WORDS = {"no", "nope", "wrong", "different", "cancel"}

    @staticmethod
    def _normalized(message: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (message or "").casefold()))

    @classmethod
    def is_workflow_request(cls, message: str) -> bool:
        return bool(set(cls._normalized(message).split()) & cls._WORKFLOW_REQUEST_WORDS)

    @classmethod
    def confirmation_response(cls, message: str) -> bool | None:
        tokens = set(cls._normalized(message).split())
        if not tokens or len(tokens) > 4:
            return None
        if tokens & cls._CONFIRMATION_WORDS and not tokens & cls._REJECTION_WORDS:
            return True
        if tokens & cls._REJECTION_WORDS and not tokens & cls._CONFIRMATION_WORDS:
            return False
        return None

    @classmethod
    def is_catalog_candidate(cls, message: str) -> bool:
        """Limit catalog I/O to workflow requests or short name-like phrases."""
        if cls.is_workflow_request(message):
            return True
        normalized_tokens = set(cls._normalized(message).split())
        if normalized_tokens & {
            "broken",
            "damage",
            "damaged",
            "error",
            "failed",
            "failure",
            "mismatch",
            "missing",
            "wrong",
        }:
            return False
        if normalized_tokens & {"how", "what", "when", "where", "why"}:
            return False
        meaningful_terms = search_terms(message)
        return 2 <= len(meaningful_terms) <= 4

    @classmethod
    def match_published_workflow(
        cls,
        message: str,
        catalog: Sequence[Dict[str, Any]],
        *,
        proposal_mode: bool = False,
    ) -> Dict[str, Any] | None:
        """Return one confident catalog match, or none when the request is ambiguous."""
        query_terms = search_terms(message)
        if not query_terms or not catalog:
            return None

        ranked = sorted(
            (
                (
                    min(
                        1.0,
                        fuzzy_relevance_score(
                            message,
                            " ".join(
                                str(item.get(field) or "")
                                for field in ("title", "workflow_code", "description")
                            ),
                        )
                        + 0.25 * fuzzy_relevance_score(
                            message, str(item.get("title") or "")
                        ),
                    ),
                    item,
                )
                for item in catalog
            ),
            key=lambda result: result[0],
            reverse=True,
        )
        top_score, top_item = ranked[0]
        request_signal = cls.is_workflow_request(message)
        # A proposal is never executed until the employee confirms it, so a
        # lower threshold is safe for natural problem descriptions.
        minimum_score = 0.30 if proposal_mode else (0.58 if request_signal else 0.82)
        if top_score < minimum_score:
            return None

        # A bare phrase can select a workflow only when it carries at least two
        # meaningful terms, such as "receive shipment". This keeps operational
        # questions like "package damaged" out of catalog-selection logic.
        if not proposal_mode and not request_signal and len(query_terms) < 2:
            return None

        runner_up_score = ranked[1][0] if len(ranked) > 1 else 0.0
        required_margin = 0.08 if proposal_mode else 0.12
        if runner_up_score >= minimum_score and top_score - runner_up_score < required_margin:
            return None
        return {**top_item, "match_score": top_score}

    @classmethod
    def is_all_steps_completion(cls, message: str) -> bool:
        """Recognize an employee attestation, not a question about completion."""
        if "?" in message:
            return False
        normalized = cls._normalized(message)
        if normalized.startswith(("are all ", "did all ", "have all ", "is everything ")):
            return False
        tokens = set(normalized.split())
        has_completion = bool(
            tokens & {"complete", "completed", "done", "finished"}
        )
        has_full_scope = bool(
            "everything" in tokens
            or tokens & {"all", "each", "every"}
            and tokens & {"process", "step", "steps", "workflow"}
            or tokens & {"entire", "whole"}
            and tokens & {"process", "workflow"}
        )
        return has_completion and has_full_scope
