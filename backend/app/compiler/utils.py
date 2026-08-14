"""Compiler Utilities and Helpers.

Provides reusable utilities for SHA256 source hashing, ID generation, text sanitization,
and graph traversal analysis (reachability & cycle detection).
"""

import re
import hashlib
import uuid
from typing import List, Set, Dict


def calculate_source_hash(markdown_text: str) -> str:
    """Calculates SHA-256 hash of OWD source markdown text."""
    if not markdown_text:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()


def generate_deterministic_uuid(namespace_key: str, name: str) -> str:
    """Generates a reproducible UUIDv5 for compiled entities."""
    ns = uuid.uuid5(uuid.NAMESPACE_DNS, namespace_key)
    return str(uuid.uuid5(ns, name))


def sanitize_code(raw_str: str, prefix: str = "") -> str:
    """Normalizes raw input strings into clean, UPPERCASE_SNAKE_CASE identifier codes."""
    if not raw_str:
        return f"{prefix}_DEFAULT" if prefix else "DEFAULT_CODE"
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', raw_str.strip()).upper()
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if prefix and not cleaned.startswith(prefix):
        return f"{prefix}_{cleaned}"
    return cleaned


def find_unreachable_states(initial_state_key: str, state_keys: Set[str], transitions: List[Dict[str, str]]) -> List[str]:
    """Traverses transitions from initial state to identify unreachable graph states."""
    if not initial_state_key or initial_state_key not in state_keys:
        return list(state_keys)

    visited: Set[str] = set()
    queue = [initial_state_key]

    adjacency: Dict[str, List[str]] = {k: [] for k in state_keys}
    for t in transitions:
        src = t.get("from_state_key")
        dst = t.get("to_state_key")
        if src in adjacency and dst in state_keys:
            adjacency[src].append(dst)

    while queue:
        curr = queue.pop(0)
        if curr not in visited:
            visited.add(curr)
            for nxt in adjacency.get(curr, []):
                if nxt not in visited:
                    queue.append(nxt)

    unreachable = [k for k in state_keys if k not in visited]
    return unreachable
