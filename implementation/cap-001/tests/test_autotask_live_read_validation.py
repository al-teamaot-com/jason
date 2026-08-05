from __future__ import annotations

import json
from pathlib import Path

import pytest

from jason_cap_001.autotask_live_read_validation import (
    AutotaskLiveReadValidator,
    LiveReadValidationError,
    LiveReadValidationRequest,
)
from jason_cap_001.autotask_ticket_provider import AutotaskTicketProvider


class FixtureTransport:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def query_tickets(self, *, ticket_number: str, company_id: str):
        self.calls.append((ticket_number, company_id))
        return [dict(self.payload)]


def build_validator() -> tuple[AutotaskLiveReadValidator, FixtureTransport]:
    transport = FixtureTransport(
        {
            "ticketNumber": "T20260805.0001",
            "companyID": "1001",
            "title": "Controlled validation ticket",
            "description": "Sensitive body content must not be emitted.",
            "createDate": "2026-08-05T12:00:00Z",
            "lastActivityDate": "2026-08-05T12:30:00Z",
            "configurationItemID": "2002",
            "contactID": "3003",
        }
    )
    provider = AutotaskTicketProvider(transport=transport)
    return (
        AutotaskLiveReadValidator(
            provider=provider,
            allowed_scope="aot-validation",
        ),
        transport,
    )


def request(*, acknowledged: bool = True, scope: str = "aot-validation"):
    return LiveReadValidationRequest(
        ticket_number="T20260805.0001",
        company_id="1001",
        scope_name=scope,
        live_read_acknowledged=acknowledged,
    )


def test_writes_redacted_hash_protected_evidence(tmp_path: Path) -> None:
    validator, transport = build_validator()
    output = tmp_path / "evidence.json"

    evidence = validator.validate(request(), output_path=output)

    assert transport.calls == [("T20260805.0001", "1001")]
    assert evidence.status == "approved"
    assert evidence.provider == "autotask"
    assert len(evidence.title_sha256) == 64
    assert len(evidence.description_sha256) == 64
    assert len(evidence.evidence_sha256) == 64

    serialized = output.read_text(encoding="utf-8")
    assert "Controlled validation ticket" not in serialized
    assert "Sensitive body content" not in serialized
    payload = json.loads(serialized)
    assert payload["ticket_number"] == "T20260805.0001"
    assert payload["company_id"] == "1001"


def test_requires_explicit_live_read_acknowledgement(tmp_path: Path) -> None:
    validator, transport = build_validator()

    with pytest.raises(LiveReadValidationError, match="acknowledgement"):
        validator.validate(
            request(acknowledged=False),
            output_path=tmp_path / "evidence.json",
        )

    assert transport.calls == []


def test_rejects_unauthorized_scope_before_provider_call(tmp_path: Path) -> None:
    validator, transport = build_validator()

    with pytest.raises(PermissionError, match="not authorized"):
        validator.validate(
            request(scope="client-production"),
            output_path=tmp_path / "evidence.json",
        )

    assert transport.calls == []


def test_refuses_to_overwrite_evidence(tmp_path: Path) -> None:
    validator, transport = build_validator()
    output = tmp_path / "evidence.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(LiveReadValidationError, match="overwrite"):
        validator.validate(request(), output_path=output)

    assert transport.calls == []


def test_rejects_output_inside_repository(monkeypatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    monkeypatch.chdir(repository)

    validator, transport = build_validator()

    with pytest.raises(LiveReadValidationError, match="outside the repository"):
        validator.validate(
            request(),
            output_path=repository / "evidence.json",
        )

    assert transport.calls == []
