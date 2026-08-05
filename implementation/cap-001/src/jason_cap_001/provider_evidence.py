from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Callable

from .adapters import TicketProvider


class ProviderEvidenceError(RuntimeError):
    """Raised when provider evidence cannot be collected safely."""


@dataclass(frozen=True, slots=True)
class ProviderTicketRecord:
    provider: str
    external_id: str
    client_id: str
    title: str
    description: str
    created_at: str
    updated_at: str | None = None
    configuration_item_id: str | None = None
    requester_identity_id: str | None = None

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        provider: str,
    ) -> ProviderTicketRecord:
        required = (
            "external_id",
            "client_id",
            "title",
            "description",
            "created_at",
        )
        missing = [field for field in required if not payload.get(field)]
        if missing:
            raise ProviderEvidenceError(
                "Provider ticket is missing required fields: "
                + ", ".join(sorted(missing))
            )

        return cls(
            provider=provider,
            external_id=str(payload["external_id"]),
            client_id=str(payload["client_id"]),
            title=str(payload["title"]),
            description=str(payload["description"]),
            created_at=str(payload["created_at"]),
            updated_at=(
                str(payload["updated_at"])
                if payload.get("updated_at") is not None
                else None
            ),
            configuration_item_id=(
                str(payload["configuration_item_id"])
                if payload.get("configuration_item_id") is not None
                else None
            ),
            requester_identity_id=(
                str(payload["requester_identity_id"])
                if payload.get("requester_identity_id") is not None
                else None
            ),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "external_id": self.external_id,
            "client_id": self.client_id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "configuration_item_id": self.configuration_item_id,
            "requester_identity_id": self.requester_identity_id,
        }


class ProviderTicketEvidenceCollector:
    """Collect one client-scoped ticket through a read-only provider gateway."""

    def __init__(
        self,
        ticket_provider: TicketProvider,
        *,
        provider_name: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        normalized_provider = provider_name.strip().lower()
        if not normalized_provider:
            raise ValueError("provider_name must be non-empty")
        self._ticket_provider = ticket_provider
        self._provider_name = normalized_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(
        self,
        request: dict[str, Any],
        *,
        client_id: str,
    ) -> list[dict[str, Any]]:
        ticket_request = request["ticket"]
        requested_provider = str(ticket_request["provider"]).strip().lower()
        requested_external_id = str(ticket_request["external_id"])

        if requested_provider != self._provider_name:
            raise ProviderEvidenceError(
                "Requested ticket provider does not match the configured gateway."
            )

        payload = self._ticket_provider.get_ticket(
            requested_external_id,
            client_id=client_id,
        )
        record = ProviderTicketRecord.from_mapping(
            payload,
            provider=self._provider_name,
        )

        if record.client_id != client_id:
            raise PermissionError(
                "Provider ticket crossed the authorized client boundary."
            )
        if record.external_id != requested_external_id:
            raise ProviderEvidenceError(
                "Provider returned a different ticket identity."
            )

        canonical = json.dumps(
            record.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = sha256(canonical).hexdigest()
        collected_at = self._clock().astimezone(timezone.utc).isoformat()

        return [
            {
                "evidence_id": f"ticket-{self._provider_name}-{digest[:16]}",
                "source": self._provider_name,
                "collected_at": collected_at,
                "summary": f"{record.title}\n\n{record.description}",
                "content_reference": (
                    f"{self._provider_name}://tickets/{record.external_id}"
                ),
                "sha256": digest,
                "client_id": record.client_id,
                "trusted_as_instruction": False,
            }
        ]
