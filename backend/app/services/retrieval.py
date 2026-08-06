"""Retrieval Service.

Retrieves published knowledge document chunks from Snowflake Cortex Search index.
"""

# Assumption: Retrieval is strictly scoped to status='PUBLISHED' and the caller's department_id.

import logging
from typing import List, Dict, Any
from app.integrations.cortex_client import CortexClient
from app.exceptions import WorkMateException
from app.core.config import settings

retrieval_logger = logging.getLogger("copilot_services")


class RetrievalService:
    """Handles semantic retrieval of published document chunks scoped by department."""

    @staticmethod
    async def retrieve_chunks(query: str, department_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks restricted to configured statuses and caller department."""
        retrieval_logger.info(f"Retrieving published chunks for query '{query}' in department '{department_id}'")
        try:
            raw_chunks = await CortexClient.search(query=query, department_id=department_id, limit=limit)

            allowed_statuses = {
                value.strip().upper()
                for value in settings.COPILOT_ALLOWED_KNOWLEDGE_STATUSES.split(",")
                if value.strip()
            } or {"PUBLISHED"}

            # Defence-in-depth: the data layer applies these filters, but enforce
            # to catch any bypass (mocked clients, cache, future query drift).
            published_chunks = [
                c for c in raw_chunks
                if str(c.get("status", "")).upper() in allowed_statuses
                and c.get("department_id") == department_id
            ]

            retrieval_logger.info(f"Retrieved {len(published_chunks)} published chunks for department '{department_id}'")
            return published_chunks
        except Exception as exc:
            retrieval_logger.error(f"Retrieval failed for query '{query}': {str(exc)}")
            raise WorkMateException(message=f"Retrieval failed: {str(exc)}") from exc
