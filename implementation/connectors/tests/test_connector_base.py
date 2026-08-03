from __future__ import annotations

from typing import Any, Mapping

import pytest

from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)


class FakeSecrets:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(
        self,
        logical_name: str,
        context: ConnectorContext,
    ) -> Mapping[str, str]:
        self.calls.append(logical_name)
        return {"token": "synthetic-token"}


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"ok": True}


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[
            tuple[
                str,
                ConnectorContext,
                Mapping[str, Any],
            ]
        ] = []

    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        self.events.append(
            (
                event_type,
                context,
                dict(details),
            )
        )


class ExampleConnector(ConnectorBase):
    provider_name = "example"
    logical_secret = "example.readonly"
    capabilities = frozenset(
        {
            "example.entity.query",
        }
    )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        return PreparedRequest(
            method="POST",
            url="https://example.invalid/entities/query",
            headers={
                "Authorization": (
                    f"Bearer {credentials['token']}"
                )
            },
            params={"page": 1},
            json={"filter": "active"},
            timeout_seconds=12.0,
            audit_operation="/entities/query",
        )


def _request(
    *,
    capability: str = "example.entity.query",
    mode: str = "observe",
) -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-connector-base-1",
            principal_id="user-1",
            organization_id="team-aot",
            client_id=None,
            capability=capability,
            mode=mode,
        )
    )


def test_executes_shared_connector_lifecycle() -> None:
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()

    connector = ExampleConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )

    result = connector.execute(_request())

    assert secrets.calls == ["example.readonly"]

    assert transport.calls == [
        {
            "method": "POST",
            "url": (
                "https://example.invalid/"
                "entities/query"
            ),
            "headers": {
                "Authorization": (
                    "Bearer synthetic-token"
                )
            },
            "params": {"page": 1},
            "json": {"filter": "active"},
            "timeout_seconds": 12.0,
        }
    ]

    assert [
        event_type
        for event_type, _, _ in audit.events
    ] == [
        "connector.requested",
        "connector.completed",
    ]

    assert audit.events[0][2] == {
        "provider": "example",
        "operation": "/entities/query",
    }
    assert audit.events[1][2] == {
        "provider": "example",
    }

    assert result.capability == (
        "example.entity.query"
    )
    assert result.provider == "example"
    assert result.data == {"ok": True}


def test_rejects_unregistered_capability_before_secret_access() -> None:
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()

    connector = ExampleConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )

    with pytest.raises(
        ConnectorAuthorizationError,
        match="not registered",
    ):
        connector.execute(
            _request(
                capability="example.entity.delete"
            )
        )

    assert secrets.calls == []
    assert transport.calls == []
    assert audit.events == []


def test_rejects_non_observe_mode_before_secret_access() -> None:
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()

    connector = ExampleConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )

    with pytest.raises(
        ConnectorAuthorizationError,
        match="read-only",
    ):
        connector.execute(
            _request(mode="execute")
        )

    assert secrets.calls == []
    assert transport.calls == []
    assert audit.events == []
