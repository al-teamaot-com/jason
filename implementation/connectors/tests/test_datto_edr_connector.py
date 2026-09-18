from __future__ import annotations

import json

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.datto_edr.connector import DattoEdrConnector


class Secrets:
    def resolve(self, logical_secret, context):
        assert logical_secret == "datto_edr.readonly"
        return {
            "api_url": "https://example.infocyte.invalid/api",
            "api_token": "super-secret-token",
        }


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
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
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": dict(params or {}),
                "json": json,
            }
        )
        return self.responses.pop(0)


def request(capability, arguments, *, mode="observe"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-edr-1",
            principal_id="person-1",
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode=mode,
        ),
        arguments=arguments,
    )
def agent_detail():
    return {
        "id": "agent-1",
        "deviceId": "rmm-device-1",
        "hostname": "aot-50282",
        "status": "Online",
        "active": True,
        "authorized": True,
        "isolated": False,
        "syncStatus": True,
        "heartbeat": "2026-09-18T12:55:58.516Z",
        "version": "3.17.1.6224",
        "hasEdrLicense": True,
        "hasAvLicense": True,
        "dattoAvEnabled": True,
        "alertCount": "5",
        "scanStatus": "completed",
        "lastAvScanTime": "2026-09-17T14:31:36.932Z",
        "lastAvScanType": "av-quick-scan",
        "eppData": {
            "dattoav": {
                "enabled": True,
                "data": {
                    "connected": True,
                    "engineReady": True,
                    "engineVersion": "8.4.2.30",
                    "coreEngineVersion": "2.1.0.95",
                    "vdfVersion": "8.21.6.116",
                    "vdfReleaseDate": "2026-09-18T06:54:27Z",
                    "eppVersion": "1.0.2609.10929",
                    "rebootRequired": False,
                },
            }
        },
    }


def test_status_read_uses_exact_rmm_device_uid_and_normalizes_av_health():
    transport = Transport([[agent_detail()]])
    audit = Audit()
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(
        request(
            "datto_edr.endpoint.status.read",
            {"device_uid": "rmm-device-1"},
        )
    )

    assert result.data["resolved"] is True
    item = result.data["resource_matches"][0]
    assert item["resource_id"] == "rmm-device-1"
    assert item["agent_id"] == "agent-1"
    assert item["datto_av"]["connected"] is True
    assert item["datto_av"]["engine_ready"] is True
    assert item["datto_av"]["vdf_version"] == "8.21.6.116"
    assert item["datto_av"]["reboot_required"] is False

    call = transport.calls[0]
    assert call["url"].endswith("/api/AgentDetails")
    assert call["headers"] == {"Accept": "application/json"}
    assert call["params"]["access_token"] == "super-secret-token"
    filt = json.loads(call["params"]["filter"])
    assert filt["where"] == {"deviceId": "rmm-device-1"}
    assert filt["limit"] == 2

    assert all(
        "super-secret-token" not in str(details)
        for _, details in audit.events
    )
    assert "super-secret-token" not in str(result.data)


def test_status_read_accepts_provider_neutral_resource_id():
    transport = Transport([[agent_detail()]])
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        request(
            "datto_edr.endpoint.status.read",
            {"resource_id": "rmm-device-1"},
        )
    )

    assert result.data["resolved"] is True
    assert result.data["resource_matches"][0]["resource_id"] == "rmm-device-1"
    filt = json.loads(transport.calls[0]["params"]["filter"])
    assert filt["where"] == {"deviceId": "rmm-device-1"}


def test_status_read_requires_durable_resource_selector():
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=Transport([]),
        audit=Audit(),
    )

    with pytest.raises(
        ValueError,
        match="requires device_uid or resource_id",
    ):
        connector.execute(
            request(
                "datto_edr.endpoint.status.read",
                {},
            )
        )


def test_status_read_preserves_ambiguity_instead_of_picking_a_hostname_match():
    other = dict(agent_detail())
    other["id"] = "agent-2"
    transport = Transport([[agent_detail(), other]])
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        request(
            "datto_edr.endpoint.status.read",
            {"device_uid": "rmm-device-1"},
        )
    )

    assert result.data["match_count"] == 2
    assert result.data["resolved"] is False


def test_alert_read_combines_detection_and_quarantine_without_inventing_compromise():
    detail = {
        "id": "alert-1",
        "agentId": "agent-1",
        "deviceId": "rmm-device-1",
        "hostname": "aot-50282",
        "name": "example.xls",
        "severity": "high",
        "sourceName": "EXP/CVE-2016-7228",
        "sourceType": "av",
        "signal": True,
        "malicious": None,
        "notMalicious": None,
        "suspicious": None,
        "sha256": "abc123",
        "data": {
            "detected": True,
            "compromised": True,
            "quarantined": True,
            "remediated": True,
            "success": True,
            "executionStatus": "Unknown",
            "threatStatus": "Quarantined",
            "detectionId": "detect-1",
            "detectionName": "EXP/CVE-2016-7228",
            "engineVersion": "8.4.2.30",
            "vdfVersion": "8.21.6.114",
            "isolated": False,
            "rebootNeeded": False,
        },
        "responseData": [{"name": "quarantine-file"}],
    }
    quarantine = [
        {
            "id": "q1",
            "agentId": "agent-1",
            "alertId": "alert-1",
            "detectionId": "detect-1",
            "status": "Quarantined",
            "threat": "EXP/CVE-2016-7228",
        }
    ]
    audit = Audit()
    transport = Transport([detail, quarantine])
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
    )

    result = connector.execute(
        request("datto_edr.alert.read", {"alert_id": "alert-1"})
    )

    assert result.data["detected"] is True
    assert result.data["quarantined"] is True
    assert result.data["malicious"] is None
    assert result.data["provider_compromised"] is True
    assert result.data["compromise_signal"] == "provider_indicated"
    assert result.data["provider_remediated"] is True
    assert result.data["execution_status"] == "Unknown"
    assert result.data["threat_status"] == "Quarantined"
    assert result.data["detection_id"] == "detect-1"
    assert result.data["engine_version"] == "8.4.2.30"
    assert result.data["vdf_version"] == "8.21.6.114"
    assert result.data["response_actions"] == ("quarantine-file",)
    assert len(transport.calls) == 2
    assert transport.calls[0]["url"].endswith("/api/AlertDetails/alert-1")
    assert transport.calls[1]["url"].endswith("/api/QuarantinedFiles")
    assert all(
        "super-secret-token" not in str(details)
        for _, details in audit.events
    )
def test_alert_search_is_bounded_and_scoped_to_exact_agent():
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=Transport([[]]),
        audit=Audit(),
    )
    result = connector.execute(
        request(
            "datto_edr.alert.search",
            {"agent_id": "agent-1", "archived": False, "limit": 20},
        )
    )
    assert result.data == {"alerts": []}
    call = connector._transport.calls[0]
    filt = json.loads(call["params"]["filter"])
    assert filt["where"] == {"agentId": "agent-1", "archived": False}
    assert filt["limit"] == 20


def test_policy_scan_and_quarantine_reads_are_get_only():
    cases = [
        (
            "datto_edr.policy.search",
            {"agent_id": "agent-1"},
            [],
        ),
        (
            "datto_edr.scan_history.search",
            {"agent_id": "agent-1", "limit": 10},
            [],
        ),
        (
            "datto_edr.quarantine.search",
            {"agent_id": "agent-1", "limit": 10},
            [],
        ),
    ]
    for capability, arguments, response in cases:
        transport = Transport([response])
        connector = DattoEdrConnector(
            secrets=Secrets(),
            transport=transport,
            audit=Audit(),
        )
        connector.execute(request(capability, arguments))
        assert transport.calls[0]["method"] == "GET"


def test_connector_rejects_write_mode_and_unregistered_capability():
    connector = DattoEdrConnector(
        secrets=Secrets(),
        transport=Transport([]),
        audit=Audit(),
    )
    with pytest.raises(Exception):
        connector.execute(
            request(
                "datto_edr.endpoint.status.read",
                {"device_uid": "rmm-device-1"},
                mode="execute",
            )
        )
    with pytest.raises(Exception):
        connector.execute(
            request("datto_edr.endpoint.isolate", {"agent_id": "agent-1"})
        )


def test_quarantine_search_requires_a_durable_scope():
    with pytest.raises(ValueError, match="requires agent_id or alert_id"):
        DattoEdrConnector._resolve_operation(
            "datto_edr.quarantine.search",
            {},
        )


def test_credentials_require_https():
    class BadSecrets:
        def resolve(self, logical_secret, context):
            return {
                "api_url": "http://example.invalid/api",
                "api_token": "secret",
            }

    connector = DattoEdrConnector(
        secrets=BadSecrets(),
        transport=Transport([]),
        audit=Audit(),
    )
    with pytest.raises(ValueError, match="HTTPS"):
        connector.execute(
            request(
                "datto_edr.endpoint.status.read",
                {"device_uid": "rmm-device-1"},
            )
        )
