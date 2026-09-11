from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest


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
    def __init__(self, resource_items):
        self.resource_items = resource_items
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
            }
        )
        if url.endswith("/v1.0/zoneInformation"):
            return {
                "url": "https://webservices3.autotask.net/atservicesrest/",
            }
        if url.endswith("/V1.0/Resources/query"):
            return {"items": list(self.resource_items)}
        return {"item": {"id": 12345, "title": "Synthetic ticket"}}


def _request() -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-impersonation",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.get",
            mode="observe",
        ),
        arguments={"ticket_id": 12345},
    )


def test_supported_read_maps_trusted_email_and_applies_impersonation_header() -> None:
    transport = _Transport(
        [{"id": 77, "email": "AL@example.com", "isActive": True}]
    )
    connector = AutotaskImpersonatingConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=_Bindings(),
    )

    result = connector.execute(_request())

    assert result.data["item"]["id"] == 12345
    assert len(transport.requests) == 3
    lookup = transport.requests[1]
    target = transport.requests[2]
    assert lookup["url"].endswith("/V1.0/Resources/query")
    assert "ImpersonationResourceId" not in lookup["headers"]
    assert "al@example.com" in lookup["params"]["search"]
    assert target["headers"]["ImpersonationResourceId"] == "77"


def test_missing_trusted_binding_fails_closed_before_requested_read() -> None:
    transport = _Transport([])
    connector = AutotaskImpersonatingConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=_Bindings(None),
    )

    with pytest.raises(PermissionError, match="AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED"):
        connector.execute(_request())

    assert len(transport.requests) == 1
    assert transport.requests[0]["url"].endswith("/v1.0/zoneInformation")


def test_zero_matching_autotask_resources_fails_before_requested_read() -> None:
    transport = _Transport([])
    connector = AutotaskImpersonatingConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=_Bindings(),
    )

    with pytest.raises(PermissionError, match="AUTOTASK_REQUESTER_RESOURCE_NOT_UNIQUE"):
        connector.execute(_request())

    assert len(transport.requests) == 2


def test_multiple_matching_autotask_resources_fail_before_requested_read() -> None:
    transport = _Transport(
        [
            {"id": 77, "email": "al@example.com", "isActive": True},
            {"id": 88, "email": "al@example.com", "isActive": True},
        ]
    )
    connector = AutotaskImpersonatingConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=_Bindings(),
    )

    with pytest.raises(PermissionError, match="AUTOTASK_REQUESTER_RESOURCE_NOT_UNIQUE"):
        connector.execute(_request())

    assert len(transport.requests) == 2


def test_inactive_resource_is_not_accepted_as_requester_identity() -> None:
    transport = _Transport(
        [{"id": 77, "email": "al@example.com", "isActive": False}]
    )
    connector = AutotaskImpersonatingConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=_Audit(),
        bindings=_Bindings(),
    )

    with pytest.raises(PermissionError, match="AUTOTASK_REQUESTER_RESOURCE_NOT_UNIQUE"):
        connector.execute(_request())

    assert len(transport.requests) == 2
