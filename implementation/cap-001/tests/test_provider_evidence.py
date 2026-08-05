from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from jason_cap_001.provider_evidence import (
    ProviderEvidenceError,
    ProviderTicketEvidenceCollector,
)


NOW = datetime(2026, 8, 5, 12, 30, tzinfo=timezone.utc)


class TicketGateway:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def get_ticket(self, ticket_id: str, *, client_id: str) -> dict:
        self.calls.append((ticket_id, client_id))
        return dict(self.payload)


def ticket_payload(**overrides) -> dict:
    payload = {
        "external_id": "T20260805.0001",
        "client_id": "client-001",
        "title": "Backup job warning",
        "description": "The overnight backup reported one warning.",
        "created_at": "2026-08-05T10:00:00Z",
        "updated_at": "2026-08-05T10:15:00Z",
        "configuration_item_id": "asset-001",
        "requester_identity_id": "contact-001",
    }
    payload.update(overrides)
    return payload


def request(*, provider: str = "autotask") -> dict:
    return {
        "ticket": {
            "provider": provider,
            "external_id": "T20260805.0001",
        }
    }


def test_collects_client_scoped_ticket_as_untrusted_evidence() -> None:
    payload = ticket_payload()
    gateway = TicketGateway(payload)
    collector = ProviderTicketEvidenceCollector(
        gateway,
        provider_name="Autotask",
        clock=lambda: NOW,
    )

    evidence = collector.collect(request(), client_id="client-001")

    canonical = json.dumps(
        {
            "provider": "autotask",
            **payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected_digest = sha256(canonical).hexdigest()

    assert gateway.calls == [("T20260805.0001", "client-001")]
    assert evidence == [
        {
            "evidence_id": f"ticket-autotask-{expected_digest[:16]}",
            "source": "autotask",
            "collected_at": "2026-08-05T12:30:00+00:00",
            "summary": (
                "Backup job warning\n\n"
                "The overnight backup reported one warning."
            ),
            "content_reference": (
                "autotask://tickets/T20260805.0001"
            ),
            "sha256": expected_digest,
            "client_id": "client-001",
            "trusted_as_instruction": False,
        }
    ]


def test_rejects_provider_mismatch_before_gateway_call() -> None:
    gateway = TicketGateway(ticket_payload())
    collector = ProviderTicketEvidenceCollector(
        gateway,
        provider_name="autotask",
    )

    with pytest.raises(ProviderEvidenceError, match="configured gateway"):
        collector.collect(
            request(provider="itglue"),
            client_id="client-001",
        )

    assert gateway.calls == []


def test_rejects_cross_client_provider_result() -> None:
    collector = ProviderTicketEvidenceCollector(
        TicketGateway(ticket_payload(client_id="client-999")),
        provider_name="autotask",
    )

    with pytest.raises(PermissionError, match="client boundary"):
        collector.collect(request(), client_id="client-001")


def test_rejects_different_ticket_identity() -> None:
    collector = ProviderTicketEvidenceCollector(
        TicketGateway(ticket_payload(external_id="T20260805.9999")),
        provider_name="autotask",
    )

    with pytest.raises(ProviderEvidenceError, match="different ticket"):
        collector.collect(request(), client_id="client-001")


def test_rejects_incomplete_provider_record() -> None:
    collector = ProviderTicketEvidenceCollector(
        TicketGateway(ticket_payload(description="")),
        provider_name="autotask",
    )

    with pytest.raises(ProviderEvidenceError, match="description"):
        collector.collect(request(), client_id="client-001")
