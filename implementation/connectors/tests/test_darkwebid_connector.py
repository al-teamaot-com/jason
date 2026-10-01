from __future__ import annotations

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.darkwebid.connector import DarkWebIdConnector


class Secrets:
    def __init__(self):
        self.calls = []
    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return {"username": "jason@teamaot.com", "password": "opaque"}


class Audit:
    def __init__(self):
        self.events = []
    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class Transport:
    def request(self, **kwargs):
        raise AssertionError("generic transport must not be used")


class Client:
    calls = []
    def __init__(self, credentials):
        assert credentials["username"] == "jason@teamaot.com"
        assert credentials["password"] == "opaque"
    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if path == "services/organization.json":
            return {"list": [{"uuid": "abc-123", "title": "Client"}]}
        return {"uuid": "abc-123", "title": "Client"}


def context(capability, *, mode="observe", organization_id="aot", client_id=None):
    return ConnectorContext(
        correlation_id="corr-darkwebid-test",
        principal_id="tech-al",
        organization_id=organization_id,
        client_id=client_id,
        capability=capability,
        mode=mode,
    )


def build():
    Client.calls.clear()
    secrets = Secrets()
    audit = Audit()
    connector = DarkWebIdConnector(
        secrets,
        Transport(),
        audit,
        client_factory=Client,
    )
    return connector, secrets, audit


def test_organization_search_is_read_only_and_paged():
    connector, secrets, audit = build()
    result = connector.execute(
        ConnectorRequest(context("darkwebid.organization.search"), {"page": 2})
    )
    assert result.data["list"][0]["uuid"] == "abc-123"
    assert Client.calls == [
        ("services/organization.json", {"page": 2, "limit": 200})
    ]
    assert secrets.calls == ["darkwebid.runtime"]
    assert audit.events[0][1] == {
        "provider": "darkwebid",
        "operation": "organization_search",
    }


def test_organization_read_uses_exact_uuid_path():
    connector, _, _ = build()
    result = connector.execute(
        ConnectorRequest(
            context("darkwebid.organization.read"),
            {"uuid": "abc-123"},
        )
    )
    assert result.data["uuid"] == "abc-123"
    assert Client.calls == [("services/organization/abc-123.json", {})]


def test_execute_mode_is_rejected_before_secret_resolution():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="read-only"):
        connector.execute(
            ConnectorRequest(
                context("darkwebid.organization.search", mode="execute"),
                {},
            )
        )
    assert secrets.calls == []


def test_client_scoped_request_is_rejected_before_secret_resolution():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="AOT-internal"):
        connector.execute(
            ConnectorRequest(
                context("darkwebid.organization.search", client_id="123"),
                {},
            )
        )
    assert secrets.calls == []


def test_non_aot_request_is_rejected_before_secret_resolution():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="AOT-internal"):
        connector.execute(
            ConnectorRequest(
                context("darkwebid.organization.search", organization_id="other"),
                {},
            )
        )
    assert secrets.calls == []


def test_invalid_uuid_is_rejected():
    connector, _, _ = build()
    with pytest.raises(ConnectorConfigurationError, match="uuid"):
        connector.execute(
            ConnectorRequest(
                context("darkwebid.organization.read"),
                {"uuid": "../bad"},
            )
        )
