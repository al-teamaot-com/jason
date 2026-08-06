from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any, Mapping

import pytest

from connectors.autotask.live_read import (
    AutotaskLiveReadError,
    AutotaskLiveReadRequest,
    GovernedAutotaskLiveRead,
)
from connectors.core.contracts import ConnectorRequest, ConnectorResult


class FakeConnector:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.requests: list[ConnectorRequest] = []

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        self.requests.append(request)
        return ConnectorResult(
            capability=request.context.capability,
            provider="autotask",
            data=self.payload,
        )


def request(**overrides: object) -> AutotaskLiveReadRequest:
    values: dict[str, object] = {
        "ticket_number": "T20260806.0001",
        "scope_name": "aot-validation",
        "allowed_scope": "aot-validation",
        "principal_id": "operator-al",
        "organization_id": "team-aot",
        "correlation_id": "corr-autotask-live-read-1",
        "live_read_acknowledged": True,
    }
    values.update(overrides)
    return AutotaskLiveReadRequest(**values)  # type: ignore[arg-type]


def ticket_payload(**overrides: object) -> Mapping[str, Any]:
    ticket: dict[str, object] = {
        "ticketNumber": "T20260806.0001",
        "companyID": 123,
        "title": "Sensitive title",
        "description": "Sensitive description",
        "createDate": "2026-08-06T12:00:00Z",
        "lastActivityDate": "2026-08-06T13:00:00Z",
        "configurationItemID": 44,
        "contactID": 55,
    }
    ticket.update(overrides)
    return {"items": [ticket]}


def test_uses_unique_ticket_lookup_and_derives_company_boundary(
    tmp_path: Path,
) -> None:
    connector = FakeConnector(ticket_payload())
    output = tmp_path / "evidence" / "autotask.json"
    service = GovernedAutotaskLiveRead(connector)

    evidence = service.validate(
        request(),
        output_path=output,
        repository_root=tmp_path / "repository",
    )

    assert evidence.logical_secret == "autotask.readonly"
    assert evidence.capability == "autotask.ticket.search"
    assert evidence.discovered_company_id == "123"
    assert evidence.company_boundary_source == "autotask-ticket"
    assert evidence.protected_values_exposed is False
    assert len(connector.requests) == 1
    connector_request = connector.requests[0]
    assert connector_request.context.mode == "observe"
    assert connector_request.context.client_id is None
    search = json.loads(connector_request.arguments["search"])
    assert search == {
        "filter": [
            {
                "op": "eq",
                "field": "ticketNumber",
                "value": "T20260806.0001",
            }
        ]
    }


def test_preserves_redacted_hash_backed_evidence(tmp_path: Path) -> None:
    output = tmp_path / "autotask.json"
    service = GovernedAutotaskLiveRead(FakeConnector(ticket_payload()))

    service.validate(
        request(),
        output_path=output,
        repository_root=tmp_path / "repository",
    )

    stored = output.read_text(encoding="utf-8")
    data = json.loads(stored)
    assert "Sensitive title" not in stored
    assert "Sensitive description" not in stored
    assert data["discovered_company_id"] == "123"
    assert data["company_boundary_source"] == "autotask-ticket"
    assert data["title_sha256"]
    assert data["description_sha256"]
    assert data["evidence_sha256"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_denies_missing_acknowledgement_before_connector_call(
    tmp_path: Path,
) -> None:
    connector = FakeConnector(ticket_payload())
    service = GovernedAutotaskLiveRead(connector)

    with pytest.raises(PermissionError, match="acknowledgement"):
        service.validate(
            request(live_read_acknowledged=False),
            output_path=tmp_path / "evidence.json",
        )

    assert connector.requests == []


def test_denies_scope_mismatch_before_connector_call(tmp_path: Path) -> None:
    connector = FakeConnector(ticket_payload())
    service = GovernedAutotaskLiveRead(connector)

    with pytest.raises(PermissionError, match="authorized scope"):
        service.validate(
            request(scope_name="other"),
            output_path=tmp_path / "evidence.json",
        )

    assert connector.requests == []


def test_denies_missing_or_invalid_company_boundary(tmp_path: Path) -> None:
    for value in (None, ""):
        service = GovernedAutotaskLiveRead(
            FakeConnector(ticket_payload(companyID=value))
        )
        with pytest.raises(AutotaskLiveReadError, match="companyID"):
            service.validate(
                request(),
                output_path=tmp_path / f"company-{value!r}.json",
            )


def test_denies_zero_or_multiple_results(tmp_path: Path) -> None:
    for payload in ({"items": []}, {"items": [{}, {}]}):
        service = GovernedAutotaskLiveRead(FakeConnector(payload))
        with pytest.raises(AutotaskLiveReadError, match="exactly one"):
            service.validate(
                request(),
                output_path=tmp_path / (str(len(payload["items"])) + ".json"),
            )


def test_denies_evidence_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    service = GovernedAutotaskLiveRead(FakeConnector(ticket_payload()))

    with pytest.raises(AutotaskLiveReadError, match="outside"):
        service.validate(
            request(),
            output_path=repository / "evidence.json",
            repository_root=repository,
        )


def test_denies_evidence_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("existing", encoding="utf-8")
    service = GovernedAutotaskLiveRead(FakeConnector(ticket_payload()))

    with pytest.raises(FileExistsError, match="overwrite"):
        service.validate(request(), output_path=output)
