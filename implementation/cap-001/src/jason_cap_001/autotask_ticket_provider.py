from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AutotaskReadError(RuntimeError):
    """Raised when an Autotask ticket cannot be read or normalized safely."""


class AutotaskTicketTransport(Protocol):
    """Minimal read-only transport boundary used by the CAP-001 adapter."""

    def query_tickets(
        self,
        *,
        ticket_number: str,
        company_id: str,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class AutotaskTicketProvider:
    """Read one exact, client-scoped Autotask ticket.

    This adapter contains no authentication, HTTP, retry, write, or secret logic.
    Those responsibilities remain behind the supplied read-only transport.
    """

    transport: AutotaskTicketTransport

    def get_ticket(self, ticket_id: str, *, client_id: str) -> dict[str, Any]:
        normalized_ticket_id = ticket_id.strip()
        normalized_client_id = client_id.strip()
        if not normalized_ticket_id:
            raise ValueError("ticket_id must be non-empty")
        if not normalized_client_id:
            raise ValueError("client_id must be non-empty")

        results = self.transport.query_tickets(
            ticket_number=normalized_ticket_id,
            company_id=normalized_client_id,
        )

        if len(results) != 1:
            raise AutotaskReadError(
                "Autotask must return exactly one ticket for the authorized client."
            )

        raw = results[0]
        returned_ticket_id = self._required(raw, "ticketNumber")
        returned_client_id = self._required(raw, "companyID")

        if returned_ticket_id != normalized_ticket_id:
            raise AutotaskReadError(
                "Autotask returned a different ticket identity."
            )
        if returned_client_id != normalized_client_id:
            raise PermissionError(
                "Autotask ticket crossed the authorized client boundary."
            )

        return {
            "external_id": returned_ticket_id,
            "client_id": returned_client_id,
            "title": self._required(raw, "title"),
            "description": self._required(raw, "description"),
            "created_at": self._required(raw, "createDate"),
            "updated_at": self._optional(raw, "lastActivityDate"),
            "configuration_item_id": self._optional(
                raw,
                "configurationItemID",
            ),
            "requester_identity_id": self._optional(raw, "contactID"),
        }

    @staticmethod
    def _required(payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if value is None or not str(value).strip():
            raise AutotaskReadError(
                f"Autotask ticket is missing required field: {field}"
            )
        return str(value).strip()

    @staticmethod
    def _optional(payload: dict[str, Any], field: str) -> str | None:
        value = payload.get(field)
        if value is None or not str(value).strip():
            return None
        return str(value).strip()
