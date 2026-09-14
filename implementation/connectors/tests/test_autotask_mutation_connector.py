from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from connectors.autotask.impersonating_connector import (
    AUTOTASK_AUTH_MODE_IMPERSONATED,
    AUTOTASK_AUTH_MODE_JASON_MANAGED,
    AUTOTASK_REQUESTER_AUTH_MODE_ENV,
)
from connectors.autotask.mutation_connector import AutotaskMutationConnector
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)


class _Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == "autotask.readonly"
        return {
            "username": "api-user@example.invalid",
            "secret": "synthetic-secret",
            "integration_code": "synthetic-integration-code",
        }


class _Audit:
    def record(self, *args, **kwargs):
        return None


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


def _connector(transport: _Transport, bindings=_Bindings()):
    return AutotaskMutationConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=bindings,
    )


def test_ticket_create_is_impersonated_and_preflighted() -> None:
    transport = _Transport()
    connector = _connector(transport)

    result = connector.execute(
        _request(
            "autotask.ticket.create",
            {"companyID": 999, "title": "Synthetic Jason acceptance ticket"},
        )
    )

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


def test_ticket_note_create_uses_ticketnotes_security_preflight() -> None:
    transport = _Transport(create_access=2)
    connector = _connector(transport)

    connector.execute(
        _request(
            "autotask.ticket.note.create",
            {
                "ticketID": 12345,
                "description": "Synthetic note",
                "noteType": 1,
                "publish": 3,
            },
        )
    )

    assert transport.requests[2]["url"].endswith(
        "/V1.0/TicketNotes/entityInformation"
    )
    assert transport.requests[3]["method"] == "POST"
    assert transport.requests[3]["url"].endswith("/V1.0/TicketNotes")


def test_update_requires_positive_durable_id_before_resource_lookup() -> None:
    transport = _Transport()
    connector = _connector(transport)

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


def test_none_profile_access_denies_before_mutation() -> None:
    transport = _Transport(update_access=0)
    connector = _connector(transport)

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


def test_jason_managed_mode_fails_before_any_provider_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )
    transport = _Transport()
    connector = _connector(transport)

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

    assert transport.requests == []


def test_missing_trusted_binding_fails_before_resource_lookup_or_mutation() -> None:
    transport = _Transport()
    connector = _connector(transport, _Bindings(None))

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


def test_ticket_delete_is_not_a_supported_mutation_capability() -> None:
    transport = _Transport()
    connector = _connector(transport)

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

    assert transport.requests == []
