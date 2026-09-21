from __future__ import annotations

import json

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.kyocera_kfs import KFS_DEFAULT_API_URL, KyoceraKfsConnector


class FakeSecrets:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def resolve(self, logical_name: str, context: ConnectorContext) -> dict[str, str]:
        self.calls.append(logical_name)
        return dict(self.values)


class FakeTransport:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.response = response or {"ok": True}
        self.calls: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.response)


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record(self, event_type, context, details) -> None:
        self.events.append((event_type, dict(details)))


def context(capability: str = "kyocera_kfs.meters.get", mode: str = "observe") -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-kfs-001",
        principal_id="tech-al",
        organization_id="aot",
        client_id="client-1",
        capability=capability,
        mode=mode,
    )


def credentials() -> dict[str, str]:
    return {
        "api_url": KFS_DEFAULT_API_URL,
        "access_id": "ACCESS-ID",
        "access_password": "ACCESS-PASSWORD",
        "request_from": "REQUEST-FROM",
        "request_to": "REQUEST-TO",
        "authorization": "AUTHORIZATION-VALUE",
        "kfs_username": "kfs-manager@example.test",
        "kfs_password": "KFS-PASSWORD",
        "headers_json": json.dumps(
            {
                "X-Test-Access": "{access_id}",
                "X-Test-From": "{request_from}",
                "Authorization": "{authorization}",
            }
        ),
        "operations_json": json.dumps(
            {
                "device_search": {
                    "method": "GET",
                    "path": "/dealer/devices",
                    "params": {"serial": "{serial_number}"},
                },
                "device_get": {
                    "method": "GET",
                    "path": "/dealer/devices/{device_id}",
                },
                "meters_get": {
                    "method": "POST",
                    "path": "/dealer/devices/{device_id}/meters",
                    "json": {
                        "user": "{kfs_username}",
                        "password": "{kfs_password}",
                    },
                },
                "supplies_get": {
                    "method": "GET",
                    "path": "/dealer/devices/{device_id}/supplies",
                },
                "alerts_list": {
                    "method": "GET",
                    "path": "/dealer/alerts",
                    "params": {"customer": "{customer_id}"},
                },
            }
        ),
    }


def build(values: dict[str, str] | None = None):
    secrets = FakeSecrets(values or credentials())
    transport = FakeTransport({"meters": [{"name": "total", "value": 1234}]})
    audit = FakeAudit()
    connector = KyoceraKfsConnector(secrets, transport, audit)
    return connector, secrets, transport, audit


def test_meter_request_uses_configured_provider_contract_without_guessing_paths() -> None:
    connector, _, _, _ = build()
    request = ConnectorRequest(
        context=context(),
        arguments={"device_id": "SERIAL-123"},
    )

    prepared = connector.prepare_request(request, credentials())

    assert prepared.method == "POST"
    assert prepared.url == "https://api.kyods.com/dealer/devices/SERIAL-123/meters"
    assert prepared.headers["X-Test-Access"] == "ACCESS-ID"
    assert prepared.headers["Authorization"] == "AUTHORIZATION-VALUE"
    assert prepared.json == {
        "user": "kfs-manager@example.test",
        "password": "KFS-PASSWORD",
    }
    assert prepared.audit_operation == "meters_get"


def test_execute_is_read_only_audited_and_returns_provider_payload() -> None:
    connector, secrets, transport, audit = build()
    request = ConnectorRequest(
        context=context(),
        arguments={"device_id": "SERIAL-123"},
    )

    result = connector.execute(request)

    assert result.provider == "kyocera_kfs"
    assert result.capability == "kyocera_kfs.meters.get"
    assert result.data["meters"][0]["value"] == 1234
    assert secrets.calls == ["kyocera_kfs.readonly"]
    assert transport.calls[0]["url"].endswith("/dealer/devices/SERIAL-123/meters")
    assert audit.events == [
        (
            "connector.requested",
            {"provider": "kyocera_kfs", "operation": "meters_get"},
        ),
        (
            "connector.completed",
            {"provider": "kyocera_kfs"},
        ),
    ]


def test_device_search_renders_request_arguments_into_query_params() -> None:
    connector, _, _, _ = build()
    prepared = connector.prepare_request(
        ConnectorRequest(
            context=context("kyocera_kfs.device.search"),
            arguments={"serial_number": "ABC123"},
        ),
        credentials(),
    )

    assert prepared.method == "GET"
    assert prepared.params == {"serial": "ABC123"}


def test_missing_credential_fails_closed() -> None:
    values = credentials()
    del values["access_password"]
    connector, _, _, _ = build(values)

    with pytest.raises(ConnectorConfigurationError, match="access_password"):
        connector.execute(
            ConnectorRequest(
                context=context(),
                arguments={"device_id": "SERIAL-123"},
            )
        )


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.kyods.com",
        "https://example.com",
        "https://user:pass@api.kyods.com",
        "https://api.kyods.com?secret=x",
    ],
)
def test_unapproved_api_url_fails_closed(api_url: str) -> None:
    values = credentials()
    values["api_url"] = api_url
    connector, _, _, _ = build(values)

    with pytest.raises(ConnectorConfigurationError, match="approved HTTPS"):
        connector.execute(
            ConnectorRequest(
                context=context(),
                arguments={"device_id": "SERIAL-123"},
            )
        )


def test_missing_template_argument_fails_closed() -> None:
    connector, _, _, _ = build()

    with pytest.raises(ConnectorConfigurationError, match="device_id"):
        connector.prepare_request(
            ConnectorRequest(context=context(), arguments={}),
            credentials(),
        )


def test_external_or_traversal_operation_path_is_rejected() -> None:
    values = credentials()
    operations = json.loads(values["operations_json"])
    operations["meters_get"]["path"] = "/../https://evil.example/{device_id}"
    values["operations_json"] = json.dumps(operations)
    connector, _, _, _ = build(values)

    with pytest.raises(ConnectorConfigurationError, match="provider-local path"):
        connector.execute(
            ConnectorRequest(
                context=context(),
                arguments={"device_id": "SERIAL-123"},
            )
        )


def test_non_observe_mode_is_rejected_by_connector_governance() -> None:
    connector, _, transport, _ = build()

    with pytest.raises(ConnectorAuthorizationError, match="read-only"):
        connector.execute(
            ConnectorRequest(
                context=context(mode="execute"),
                arguments={"device_id": "SERIAL-123"},
            )
        )

    assert transport.calls == []


def test_unregistered_capability_is_rejected_before_transport() -> None:
    connector, _, transport, _ = build()

    with pytest.raises(ConnectorAuthorizationError, match="not registered"):
        connector.execute(
            ConnectorRequest(
                context=context("kyocera_kfs.remote.configure"),
                arguments={"device_id": "SERIAL-123"},
            )
        )

    assert transport.calls == []
