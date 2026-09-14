from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from connectors.autotask.impersonating_connector import (
    AUTOTASK_AUTH_MODE_IMPERSONATED,
    AUTOTASK_AUTH_MODE_JASON_MANAGED,
    AUTOTASK_REQUESTER_AUTH_MODE_ENV,
)
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
)
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)


class _Secrets:
    def __init__(self) -> None:
        self.logical_names: list[str] = []

    def resolve(self, logical_name, context):
        del context
        self.logical_names.append(str(logical_name))
        assert logical_name == "autotask.write"
        return {
            "username": "write-api-user@example.invalid",
            "secret": "synthetic-write-secret",
            "integration_code": "synthetic-integration-code",
        }


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, event_type, context, details):
        del context
        self.events.append((str(event_type), dict(details)))


@dataclass(frozen=True)
class _Binding:
    jason_identity_id: str = "person-al"
    email_address: str = "al@example.com"


class _Bindings:
    def __init__(self, binding=_Binding()):
        self.binding = binding

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        if self.binding is None or self.binding.jason_identity_id != jason_identity_id:
            return None
        return self.binding


class _Transport:
    def __init__(
        self,
        *,
        resource_items=None,
        create_access: int = 1,
        update_access: int = 1,
    ) -> None:
        self.resource_items = resource_items or [
            {"id": 77, "email": "al@example.com", "isActive": True}
        ]
        self.create_access = create_access
        self.update_access = update_access
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
            }
        )
        if url.endswith("/v1.0/zoneInformation"):
            return {
                "url": "https://webservices3.autotask.net/atservicesrest/",
            }
        if url.endswith("/V1.0/Resources/query"):
            return {"items": list(self.resource_items)}
        if url.endswith("/entityInformation"):
            return {
                "userAccessForCreate": self.create_access,
                "userAccessForUpdate": self.update_access,
            }
        return {"itemId": 12345}


def _request(capability: str, payload: Mapping[str, Any]) -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-autotask-write",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode="execute",
        ),
        arguments={"payload": payload},
    )


@pytest.fixture(autouse=True)
def _provider_native_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_IMPERSONATED,
    )
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")


def _connector(
    transport: _Transport,
    bindings=_Bindings(),
    secrets: _Secrets | None = None,
    audit: _Audit | None = None,
):
    return AutotaskMutationConnector(
        secrets=secrets or _Secrets(),
        transport=transport,
        audit=audit or _Audit(),
        bindings=bindings,
    )


def _event_names(audit: _Audit) -> list[str]:
    return [event for event, _ in audit.events]


def test_ticket_create_is_impersonated_preflighted_and_audited() -> None:
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    result = connector.execute(
        _request(
            "autotask.ticket.create",
            {"companyID": 999, "title": "Synthetic Jason acceptance ticket"},
        )
    )

    assert secrets.logical_names == ["autotask.write"]
    assert result.data["itemId"] == 12345
    assert [request["method"] for request in transport.requests] == [
        "GET",
        "GET",
        "GET",
        "POST",
    ]
    lookup = transport.requests[1]
    preflight = transport.requests[2]
    mutation = transport.requests[3]
    assert lookup["url"].endswith("/V1.0/Resources/query")
    assert "ImpersonationResourceId" not in lookup["headers"]
    assert preflight["url"].endswith("/V1.0/Tickets/entityInformation")
    assert preflight["headers"]["ImpersonationResourceId"] == "77"
    assert mutation["url"].endswith("/V1.0/Tickets")
    assert mutation["headers"]["ImpersonationResourceId"] == "77"
    assert mutation["json"] == {
        "companyID": 999,
        "title": "Synthetic Jason acceptance ticket",
    }
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.completed",
    ]
    assert audit.events[0][1] == {
        "provider": "autotask",
        "capability": "autotask.ticket.create",
    }
    assert "synthetic-write-secret" not in repr(audit.events)
    assert "al@example.com" not in repr(audit.events)


def test_ticket_note_create_uses_ticketnotes_security_preflight() -> None:
    transport = _Transport(create_access=2)
    connector = _connector(transport)

    connector.execute(
        _request(
            "autotask.ticket.note.create",
            {
                "ticketID": 12345,
                "description": "Synthetic note",
                "noteType": 3,
                "publish": 1,
            },
        )
    )

    assert transport.requests[2]["url"].endswith(
        "/V1.0/TicketNotes/entityInformation"
    )
    assert transport.requests[3]["method"] == "POST"
    assert transport.requests[3]["url"].endswith(
        "/V1.0/Tickets/12345/Notes"
    )


def test_ticket_note_update_uses_ticketnotes_security_preflight_and_child_route() -> None:
    transport = _Transport(update_access=2)
    connector = _connector(transport)

    connector.execute(
        _request(
            "autotask.ticket.note.update",
            {
                "ticketID": 12345,
                "id": 67890,
                "description": "Updated synthetic note",
                "noteType": 3,
                "publish": 1,
            },
        )
    )

    assert transport.requests[2]["url"].endswith(
        "/V1.0/TicketNotes/entityInformation"
    )
    assert transport.requests[3]["method"] == "PATCH"
    assert transport.requests[3]["url"].endswith(
        "/V1.0/Tickets/12345/Notes"
    )
    assert transport.requests[3]["json"]["id"] == 67890
    assert transport.requests[3]["json"]["ticketID"] == 12345


def test_mutation_connector_does_not_offer_or_resolve_credentials_for_reads() -> None:
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    assert "autotask.ticket.search" not in connector.capabilities
    assert "autotask.ticket.get" not in connector.capabilities

    with pytest.raises(
        ConnectorAuthorizationError,
        match="not registered",
    ):
        connector.execute(
            _request(
                "autotask.ticket.search",
                {},
            )
        )

    assert secrets.logical_names == []
    assert transport.requests == []
    assert audit.events == []


def test_execution_is_disabled_by_default_before_secret_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AUTOTASK_MUTATION_ENABLED_ENV, raising=False)
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_MUTATION_EXECUTION_DISABLED",
    ):
        connector.execute(
            _request(
                "autotask.ticket.create",
                {"companyID": 999, "title": "Must not be sent"},
            )
        )

    assert secrets.logical_names == []
    assert transport.requests == []
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]
    assert audit.events[-1][1]["error_type"] == "PermissionError"


def test_invalid_enablement_value_fails_closed_before_secret_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "yes")
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    with pytest.raises(RuntimeError, match="AUTOTASK_MUTATION_ENABLEMENT_INVALID"):
        connector.execute(
            _request(
                "autotask.ticket.create",
                {"companyID": 999, "title": "Must not be sent"},
            )
        )

    assert secrets.logical_names == []
    assert transport.requests == []
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]
    assert audit.events[-1][1]["error_type"] == "RuntimeError"


def test_update_requires_positive_durable_id_before_resource_lookup() -> None:
    transport = _Transport()
    audit = _Audit()
    connector = _connector(transport, audit=audit)

    with pytest.raises(ValueError, match="positive numeric id"):
        connector.execute(
            _request(
                "autotask.ticket.update",
                {"status": 5},
            )
        )

    # Zone discovery occurs while compiling the bounded provider request, but
    # requester lookup/preflight/mutation do not occur after the invalid body.
    assert len(transport.requests) == 1
    assert transport.requests[0]["url"].endswith("/v1.0/zoneInformation")
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]
    assert audit.events[-1][1]["error_type"] == "ValueError"


def test_none_profile_access_denies_before_mutation_and_is_audited() -> None:
    transport = _Transport(update_access=0)
    audit = _Audit()
    connector = _connector(transport, audit=audit)

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_REQUESTER_OPERATION_NOT_PERMITTED",
    ):
        connector.execute(
            _request(
                "autotask.ticket.update",
                {"id": 12345, "status": 5},
            )
        )

    assert len(transport.requests) == 3
    assert transport.requests[-1]["url"].endswith(
        "/V1.0/Tickets/entityInformation"
    )
    assert not any(
        request["method"] == "PATCH"
        for request in transport.requests
    )
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]
    assert audit.events[-1][1] == {
        "provider": "autotask",
        "capability": "autotask.ticket.update",
        "error_type": "PermissionError",
    }


def test_jason_managed_mode_fails_before_secret_resolution_or_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_WRITE_REQUIRES_REQUESTER_IMPERSONATION",
    ):
        connector.execute(
            _request(
                "autotask.ticket.create",
                {"companyID": 999, "title": "Must not be sent"},
            )
        )

    assert secrets.logical_names == []
    assert transport.requests == []
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]


def test_missing_trusted_binding_fails_before_resource_lookup_or_mutation() -> None:
    transport = _Transport()
    audit = _Audit()
    connector = _connector(transport, _Bindings(None), audit=audit)

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED",
    ):
        connector.execute(
            _request(
                "autotask.ticket.create",
                {"companyID": 999, "title": "Must not be sent"},
            )
        )

    assert len(transport.requests) == 1
    assert transport.requests[0]["url"].endswith("/v1.0/zoneInformation")
    assert _event_names(audit) == [
        "connector.mutation.requested",
        "connector.mutation.failed",
    ]


def test_ticket_delete_is_not_a_supported_mutation_capability() -> None:
    transport = _Transport()
    secrets = _Secrets()
    audit = _Audit()
    connector = _connector(transport, secrets=secrets, audit=audit)

    with pytest.raises(
        ConnectorAuthorizationError,
        match="not registered",
    ):
        connector.execute(
            _request(
                "autotask.ticket.delete",
                {"id": 12345},
            )
        )

    assert secrets.logical_names == []
    assert transport.requests == []
    assert audit.events == []
