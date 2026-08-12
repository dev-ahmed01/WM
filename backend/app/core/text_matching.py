"""Deterministic typo and domain-language matching shared across Copilot layers."""

from difflib import SequenceMatcher
import re
from typing import List


_STOP_WORDS = {
    "a", "about", "all", "an", "and", "are", "can", "could", "currently", "do", "does",
    "fetch", "find", "for", "get", "give", "how", "i", "if", "in", "is", "it", "launch",
    "load", "me", "my", "navigate", "need", "next", "now", "of", "on", "open", "our", "please", "procedure",
    "process", "show", "sop", "start", "step", "steps", "take",
    "its", "not", "purpose", "reason", "should", "tell", "the", "this", "to", "trying",
    "want", "what", "when", "where", "why", "with", "workflow", "would", "you",
}

_DOMAIN_EQUIVALENTS = {
    "box": "handling_unit",
    "boxes": "handling_unit",
    "carton": "handling_unit",
    "cartons": "handling_unit",
    "container": "handling_unit",
    "containers": "handling_unit",
    "package": "handling_unit",
    "packages": "handling_unit",
    "pallet": "handling_unit",
    "pallets": "handling_unit",
    "damage": "damage",
    "damaged": "damage",
    "damages": "damage",
    "check": "verify",
    "checked": "verify",
    "checking": "verify",
    "mismatched": "mismatch",
    "mismatches": "mismatch",
}

_NEGATIVE_MATCH_PATTERN = re.compile(
    r"\b(?:do|does|did|will|would)?\s*(?:not|n['’]t)\s+match(?:ed|es|ing)?\b",
    re.IGNORECASE,
)


def _is_stop_word(term: str) -> bool:
    if term in _STOP_WORDS:
        return True
    if len(term) < 3:
        return False
    return any(
        abs(len(term) - len(stop_word)) <= 1
        and term[0] == stop_word[0]
        and SequenceMatcher(None, term, stop_word).ratio() >= 0.82
        for stop_word in _STOP_WORDS
    )


def search_terms(query: str) -> List[str]:
    normalized_query = _NEGATIVE_MATCH_PATTERN.sub("mismatch", query or "")
    terms = re.findall(r"[a-z0-9][a-z0-9_-]{1,}", normalized_query.lower())
    result: List[str] = []
    for term in terms:
        if not _is_stop_word(term) and term not in result:
            result.append(term)
    return result[:8]


def _canonical_domain_token(token: str) -> str:
    exact = _DOMAIN_EQUIVALENTS.get(token)
    if exact:
        return exact
    if len(token) < 4:
        return token
    best_key = max(
        (
            key
            for key in _DOMAIN_EQUIVALENTS
            if key[0] == token[0] and abs(len(key) - len(token)) <= 2
        ),
        key=lambda key: SequenceMatcher(None, token, key).ratio(),
        default="",
    )
    if best_key and SequenceMatcher(None, token, best_key).ratio() >= 0.82:
        return _DOMAIN_EQUIVALENTS[best_key]
    return token


def fuzzy_relevance_score(query: str, candidate_content: str) -> float:
    """Score typo-tolerant token overlap without changing or generating SOP text."""
    query_tokens = [_canonical_domain_token(token) for token in search_terms(query)]
    if not query_tokens:
        return 0.0
    raw_candidate_tokens = set(
        re.findall(r"[a-z0-9][a-z0-9_-]{1,}", (candidate_content or "").lower())
    )
    raw_candidate_tokens.update(
        part
        for token in tuple(raw_candidate_tokens)
        for part in re.split(r"[_-]+", token)
        if len(part) >= 2
    )
    # Keep raw vocabulary for typo matching as well as canonical domain aliases.
    candidate_tokens = raw_candidate_tokens | {
        _DOMAIN_EQUIVALENTS.get(token, token) for token in raw_candidate_tokens
    }
    qualities: List[float] = []
    for query_token in query_tokens:
        if query_token in candidate_tokens:
            qualities.append(1.0)
            continue
        if len(query_token) < 4:
            continue
        threshold = 0.72 if len(query_token) >= 6 else 0.74
        best = max(
            (
                SequenceMatcher(None, query_token, candidate_token).ratio()
                for candidate_token in candidate_tokens
                if candidate_token
                and not (
                    query_token in {"match", "matched", "matches", "matching"}
                    and candidate_token.startswith("mismatch")
                )
                and candidate_token[0] == query_token[0]
                and abs(len(candidate_token) - len(query_token)) <= 2
            ),
            default=0.0,
        )
        if best >= threshold:
            qualities.append(best)
    denominator = min(len(query_tokens), 4)
    return round(min(1.0, sum(sorted(qualities, reverse=True)[:4]) / denominator), 6)
