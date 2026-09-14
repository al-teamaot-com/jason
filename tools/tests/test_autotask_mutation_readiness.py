from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tools.autotask_mutation_readiness import (
    DEFAULT_AUTOTASK_WRITE_ROLE_ID_PATH,
    DEFAULT_AUTOTASK_WRITE_SECRET_ID_PATH,
    ReadOnlyReadinessTransport,
    _synthetic_payload,
    run,
)


class _Delegate:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def request(
        self,
        *,
        method,
        url,
        headers,
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        del headers, params, json, timeout_seconds
        self.calls.append(f"{method} {url}")
        return {"ok": True}


def test_readiness_transport_blocks_non_get_before_delegate_io() -> None:
    delegate = _Delegate()
    transport = ReadOnlyReadinessTransport(delegate=delegate)

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_READINESS_PROVIDER_WRITE_BLOCKED",
    ):
        transport.request(
            method="POST",
            url="https://autotask.invalid/V1.0/Tickets",
            headers={},
            json={"title": "must-not-send"},
        )

    assert delegate.calls == []
    assert transport.calls == []


def test_readiness_transport_allows_only_safe_get_and_drops_body() -> None:
    delegate = _Delegate()
    transport = ReadOnlyReadinessTransport(delegate=delegate)

    result = transport.request(
        method="GET",
        url="https://autotask.invalid/V1.0/Tickets/entityInformation",
        headers={"ImpersonationResourceId": "77"},
        json={"must": "not reach delegate"},
    )

    assert result == {"ok": True}
    assert delegate.calls == [
        "GET https://autotask.invalid/V1.0/Tickets/entityInformation"
    ]
    assert transport.calls == [
        {
            "method": "GET",
            "zone_information": False,
            "resource_lookup": False,
            "entity_information": True,
            "impersonation_header_present": True,
            "request_body_present": True,
        }
    ]


def test_synthetic_payloads_are_non_real_compilation_only_values() -> None:
    assert _synthetic_payload("autotask.ticket.create") == {
        "companyID": 1,
        "title": "JASON_READINESS_NOT_SENT",
    }
    assert _synthetic_payload("autotask.ticket.update") == {"id": 1}
    assert _synthetic_payload("autotask.ticket.note.create") == {
        "ticketID": 1,
        "description": "JASON_READINESS_NOT_SENT",
    }
    assert _synthetic_payload("autotask.ticket.note.update") == {
        "ticketID": 1,
        "id": 1,
    }
    with pytest.raises(ValueError, match="OPERATION_NOT_APPROVED"):
        _synthetic_payload("autotask.ticket.delete")


def test_defaults_point_only_to_dedicated_autotask_write_approle() -> None:
    assert DEFAULT_AUTOTASK_WRITE_ROLE_ID_PATH == Path(
        "/opt/jason/bootstrap/secrets/openbao/autotask-write-approle/role-id"
    )
    assert DEFAULT_AUTOTASK_WRITE_SECRET_ID_PATH == Path(
        "/opt/jason/bootstrap/secrets/openbao/autotask-write-approle/secret-id"
    )


def test_check_only_contacts_no_provider_or_secret_store(tmp_path, capsys) -> None:
    args = argparse.Namespace(
        principal_id="person-al",
        correlation_id="corr-check-only",
        evidence_output=tmp_path.parent / "readiness-evidence.json",
        bindings_db=tmp_path / "bindings.sqlite3",
        microsoft_boundary_db=tmp_path / "boundaries.sqlite3",
        microsoft_role_id_path=tmp_path / "missing-ms-role",
        microsoft_secret_id_path=tmp_path / "missing-ms-secret",
        expected_principal_email=None,
        role_id_path=tmp_path / "missing-autotask-write-role",
        secret_id_path=tmp_path / "missing-autotask-write-secret",
        openbao_url="http://127.0.0.1:8200",
        check_only=True,
        live_read=False,
    )

    assert run(args) is None
    output = capsys.readouterr().out
    assert '"network_contacted": false' in output
    assert '"provider_write": false' in output
    assert '"compiled_mutation_dispatched": false' in output
    assert '"credential_logical_name": "autotask.write"' in output
