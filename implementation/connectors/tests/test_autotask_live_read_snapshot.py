from __future__ import annotations

import json

from connectors.autotask.live_read import (
    AutotaskLiveReadRequest,
    GovernedAutotaskLiveRead,
)
from connectors.core.contracts import ConnectorResult


class FakeConnector:
    provider_name = "autotask"
    capabilities = frozenset({"autotask.ticket.search"})

    def execute(self, request):
        return ConnectorResult(
            capability="autotask.ticket.search",
            provider="autotask",
            data={
                "items": [
                    {
                        "ticketNumber": "T20260805.0064",
                        "companyID": 208,
                        "title": "Sensitive ticket title",
                        "description": "Sensitive ticket description",
                        "createDate": "2026-08-05T17:16:45.500Z",
                        "lastActivityDate": "2026-08-05T17:17:03.153Z",
                    }
                ]
            },
        )


def test_read_ticket_returns_ephemeral_snapshot_and_redacted_evidence(tmp_path) -> None:
    service = GovernedAutotaskLiveRead(FakeConnector())
    output = tmp_path / "autotask-evidence.json"

    snapshot, evidence = service.read_ticket(
        AutotaskLiveReadRequest(
            ticket_number="T20260805.0064",
            scope_name="aot-internal-ticket-analysis",
            allowed_scope="aot-internal-ticket-analysis",
            principal_id="operator-al",
            organization_id="aot",
            correlation_id="corr-1",
            live_read_acknowledged=True,
        ),
        output_path=output,
    )

    assert snapshot.title == "Sensitive ticket title"
    assert snapshot.description == "Sensitive ticket description"
    assert snapshot.company_id == "208"
    assert evidence.protected_values_exposed is False

    persisted = output.read_text(encoding="utf-8")
    assert "Sensitive ticket title" not in persisted
    assert "Sensitive ticket description" not in persisted
    payload = json.loads(persisted)
    assert payload["title_sha256"]
    assert payload["description_sha256"]
    assert output.stat().st_mode & 0o777 == 0o600
