# Escalation Service for low-confidence Copilot responses

import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.core.config import settings
from app.repositories.escalation_repository import EscalationRepository
from app.exceptions.custom_exceptions import ExternalServiceException, NotFoundException

class EscalationService:
    """Manages escalation lifecycle and triggers n8n notification webhooks."""

    def __init__(self, repository: Optional[EscalationRepository] = None):
        self.repository = repository or EscalationRepository()

    async def escalate(self, conversation_message_id: str, reason: str) -> str:
        """
        Creates an escalations row with status='open', triggers an n8n webhook (notify supervisor),
        and returns the generated escalation id.
        """
        escalation_id = self.repository.create(
            conversation_message_id=conversation_message_id,
            reason=reason
        )

        # Trigger n8n supervisor notification webhook asynchronously
        n8n_webhook_url = f"{settings.N8N_BASE_URL}/webhook/escalation-webhook"
        payload = {
            "escalation_id": escalation_id,
            "conversation_message_id": conversation_message_id,
            "reason": reason,
            "triggered_at": datetime.utcnow().isoformat()
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(n8n_webhook_url, json=payload)
                if response.status_code in (200, 201, 202):
                    self.mark_notified(escalation_id)
        except Exception as exc:
            # Log error without failing escalation database creation
            print(f"[WARNING] n8n Escalation Webhook notification failed: {str(exc)}")

        return escalation_id

    def mark_notified(self, escalation_id: str) -> bool:
        """Updates the escalation status to 'notified' and sets notified_at timestamp."""
        success = self.repository.update_status(
            escalation_id=escalation_id,
            status="notified",
            notified_at=datetime.utcnow()
        )
        if not success:
            raise NotFoundException(message=f"Escalation {escalation_id} not found.")
        return True

    def resolve(self, escalation_id: str, resolution_note: str) -> bool:
        """Resolves an open escalation with supervisor notes."""
        success = self.repository.resolve(
            escalation_id=escalation_id,
            resolution_note=resolution_note
        )
        if not success:
            raise NotFoundException(message=f"Escalation {escalation_id} not found.")
        return True

    def create_external_ticket(self, escalation_id: str) -> Dict[str, Any]:
        """
        OPTIONAL: Stub for enterprise external ticketing (e.g. Jira/ServiceNow integration).
        Pending confirmation on enterprise tool integrations.
        """
        # TODO: Implement Jira API client when enterprise ticketing scope is confirmed.
        return {
            "status": "STUBBED",
            "escalation_id": escalation_id,
            "external_ticket_id": None,
            "message": "Jira ticketing integration is pending enterprise scope confirmation."
        }

    def list_escalations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists escalation records for administrative/manager analytics views."""
        return self.repository.list_all(limit=limit, offset=offset)
