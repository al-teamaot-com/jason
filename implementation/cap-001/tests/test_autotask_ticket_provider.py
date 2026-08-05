from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from jason_cap_001.autotask_ticket_provider import (
    AutotaskReadError,
    AutotaskTicketProvider,
)


@dataclass
class StubTransport:
    results: list[dict[str, Any]]
    calls: list[dict[str, str]] = field(default_factory=list)

    def query_tickets(
        self,
        *,
        ticket_number: str,
        company_id: str,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "ticket_number": ticket_number,
                "company_id": company_id,
            }
        )
        return self.results


def ticket(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ticketNumber": "T20260805.0001",
        "companyID": 42,
        "title": "Workstation is offline",
        "description": "The workstation stopped checking in.",
        "createDate": "2026-08-05T11:30:00Z",
        "lastActivityDate": "2026-08-05T12:00:00Z",
        "configurationItemID": 9001,
        "contactID": 501,
    }
    payload.update(overrides)
    return payload


def test_reads_and_normalizes_one_exact_ticket() -> None:
    transport = StubTransport([ticket()])
    provider = AutotaskTicketProvider(transport)

    result = provider.get_ticket(
        "T20260805.0001",
        client_id="42",
    )

    assert transport.calls == [
        {
            "ticket_number": "T20260805.0001",
            "company_id": "42",
        }
    ]
    assert result == {
        "external_id": "T20260805.0001",
        "client_id": "42",
        "title": "Workstation is offline",
        "description": "The workstation stopped checking in.",
        "created_at": "2026-08-05T11:30:00Z",
        "updated_at": "2026-08-05T12:00:00Z",
        "configuration_item_id": "9001",
        "requester_identity_id": "501",
    }


def test_rejects_zero_or_multiple_results() -> None:
    with pytest.raises(AutotaskReadError, match="exactly one"):
        AutotaskTicketProvider(StubTransport([])).get_ticket(
            "T20260805.0001",
            client_id="42",
        )

    with pytest.raises(AutotaskReadError, match="exactly one"):
        AutotaskTicketProvider(
            StubTransport([ticket(), ticket()])
        ).get_ticket(
            "T20260805.0001",
            client_id="42",
        )


def test_rejects_cross_client_result() -> None:
    provider = AutotaskTicketProvider(
        StubTransport([ticket(companyID=99)])
    )

    with pytest.raises(PermissionError, match="client boundary"):
        provider.get_ticket(
            "T20260805.0001",
            client_id="42",
        )


def test_rejects_different_ticket_identity() -> None:
    provider = AutotaskTicketProvider(
        StubTransport([ticket(ticketNumber="T20260805.9999")])
    )

    with pytest.raises(AutotaskReadError, match="different ticket"):
        provider.get_ticket(
            "T20260805.0001",
            client_id="42",
        )


@pytest.mark.parametrize(
    "field",
    [
        "ticketNumber",
        "companyID",
        "title",
        "description",
        "createDate",
    ],
)
def test_rejects_missing_required_fields(field: str) -> None:
    provider = AutotaskTicketProvider(
        StubTransport([ticket(**{field: None})])
    )

    with pytest.raises(AutotaskReadError, match=field):
        provider.get_ticket(
            "T20260805.0001",
            client_id="42",
        )


def test_allows_missing_optional_fields() -> None:
    provider = AutotaskTicketProvider(
        StubTransport(
            [
                ticket(
                    lastActivityDate=None,
                    configurationItemID=None,
                    contactID=None,
                )
            ]
        )
    )

    result = provider.get_ticket(
        "T20260805.0001",
        client_id="42",
    )

    assert result["updated_at"] is None
    assert result["configuration_item_id"] is None
    assert result["requester_identity_id"] is None
