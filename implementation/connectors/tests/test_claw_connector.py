from __future__ import annotations

from dataclasses import dataclass

import pytest

from connectors.claw.connector import (
    CLAW_ARTIFACT_READ,
    CLAW_BRIDGE_READ,
    CLAW_STATUS_READ,
    CLAW_TASK_REQUEST_CREATE,
    CLAW_TASK_REQUEST_SEARCH,
    ClawConnector,
)
from connectors.core.contracts import ConnectorContext, ConnectorRequest


@dataclass
class FakeSecrets:
    values: dict[str, str]

    def resolve(self, logical_name, context):
        assert logical_name == "claw.runtime"
        return self.values


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeClient:
    calls = []

    def __init__(self, credentials):
        assert credentials["bearer_token"] == "secret"
        type(self).calls = []

    def call_tool(self, name, arguments):
        type(self).calls.append((name, dict(arguments)))
        return {"ok": True, "tool": name}


def _request(capability, arguments=None, mode="observe"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-1",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode=mode,
        ),
        arguments=arguments or {},
    )


def _connector():
    return ClawConnector(
        FakeSecrets(
            {
                "mcp_url": "https://192.168.12.41/mcp",
                "bearer_token": "secret",
                "ca_cert_pem": "-----BEGIN CERTIFICATE-----
X
-----END CERTIFICATE-----",
            }
        ),
        FakeAudit(),
        client_factory=FakeClient,
    )


@pytest.mark.parametrize(
    ("capability", "tool"),
    [
        (CLAW_BRIDGE_READ, "openclaw_bridge_status"),
        (CLAW_STATUS_READ, "openclaw_status_summary"),
    ],
)
def test_simple_reads_map_to_exact_bridge_tools(capability, tool):
    connector = _connector()
    result = connector.execute(_request(capability))
    assert result.provider == "claw"
    assert result.data["ok"] is True
    assert FakeClient.calls == [(tool, {})]


def test_artifact_read_is_allowlisted_and_bounded():
    connector = _connector()
    connector.execute(
        _request(
            CLAW_ARTIFACT_READ,
            {"key": "daily_ops_latest", "max_bytes": 1234},
        )
    )
    assert FakeClient.calls == [
        ("openclaw_read_artifact", {"key": "daily_ops_latest", "maxBytes": 1234})
    ]
    with pytest.raises(ValueError, match="allowlisted"):
        connector.execute(_request(CLAW_ARTIFACT_READ, {"key": "../../etc/passwd"}))


def test_task_request_search_is_bounded():
    connector = _connector()
    connector.execute(_request(CLAW_TASK_REQUEST_SEARCH, {"limit": 10}))
    assert FakeClient.calls == [("openclaw_list_task_requests", {"limit": 10})]
    with pytest.raises(ValueError, match="between 1 and 100"):
        connector.execute(_request(CLAW_TASK_REQUEST_SEARCH, {"limit": 101}))


def test_task_request_create_is_execute_only_and_server_attributed():
    connector = _connector()
    with pytest.raises(Exception, match="execute mode"):
        connector.execute(_request(CLAW_TASK_REQUEST_CREATE, {"title": "abc", "body": "x"}))
    connector.execute(
        _request(
            CLAW_TASK_REQUEST_CREATE,
            {"title": "Review automation", "body": "Inspect latest run.", "priority": "high"},
            mode="execute",
        )
    )
    assert FakeClient.calls == [
        (
            "openclaw_create_task_request",
            {
                "title": "Review automation",
                "body": "Inspect latest run.",
                "priority": "high",
                "requestedBy": "Jason",
                "correlationId": "corr-1",
            },
        )
    ]
