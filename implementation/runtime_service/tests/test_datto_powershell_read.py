from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.datto_rmm.auth import DattoRmmAccessToken
from connectors.datto_rmm.readonly_powershell import DattoRmmReadOnlyPowerShellPolicy
from jason_runtime import datto_powershell_read as module
from jason_runtime.datto_component_scope import DATTO_AD_HOC_POWERSHELL_UID


class Secrets:
    def resolve(self, logical_name, context):
        return {
            "api_url": "https://example.invalid",
            "api_key": "key",
            "api_secret": "secret",
        }


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class Transport:
    def __init__(self):
        self.calls = []

    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
        self.calls.append((method, url, json))
        if method == "GET" and "/api/v2/device/" in url and "/results/" not in url:
            return {"uid": "device-1"}
        if method == "PUT" and url.endswith("/api/v2/device/device-1/quickjob"):
            return {"uid": "job-1"}
        if method == "GET" and url.endswith("/api/v2/job/job-1"):
            return {"uid": "job-1", "status": "completed"}
        if method == "GET" and url.endswith("/stdout"):
            return [{"componentUid": DATTO_AD_HOC_POWERSHELL_UID, "stdData": "Running\n"}]
        if method == "GET" and url.endswith("/stderr"):
            return [{"componentUid": DATTO_AD_HOC_POWERSHELL_UID, "stdData": ""}]
        raise AssertionError((method, url, json))


def request(command="Get-Service"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-1",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability=module.DATTO_RMM_POWERSHELL_READ_PROVIDER_CAPABILITY,
            mode="observe",
        ),
        arguments={"device_uid": "device-1", "command": command},
    )


def connector(monkeypatch):
    monkeypatch.setattr(
        module,
        "acquire_access_token",
        lambda credentials: DattoRmmAccessToken(access_token="token"),
    )
    return module.DattoRmmPowerShellReadConnector(
        secrets=Secrets(),
        transport=Transport(),
        audit=Audit(),
        sleeper=lambda _: None,
    )


def test_capability_definition_is_read_only_and_single_attempt():
    definition = module._capability_definition(now=datetime.now(timezone.utc))

    assert definition.capability_name == "endpoint.powershell.read"
    assert definition.metadata["read_only"] == "true"
    assert definition.metadata["endpoint_state_mutation_allowed"] == "false"
    assert definition.approval.required is False
    assert definition.maximum_attempts == 1


def test_general_read_only_pipeline_runs_through_exact_component(monkeypatch):
    c = connector(monkeypatch)
    command = (
        "Get-Process | Sort-Object WorkingSet -Descending | "
        "Select-Object -First 20"
    )

    result = c.execute(request(command))

    assert result.data["status"] == "succeeded"
    assert result.data["stdout"] == "Running\n"
    assert result.data["stderr"] == ""
    assert result.data["component_uid"] == DATTO_AD_HOC_POWERSHELL_UID

    puts = [call for call in c._transport.calls if call[0] == "PUT"]
    assert len(puts) == 1
    body = puts[0][2]
    assert body["jobComponent"]["componentUid"] == DATTO_AD_HOC_POWERSHELL_UID
    assert body["jobComponent"]["variables"] == [
        {"name": "usrInput", "value": command}
    ]


@pytest.mark.parametrize(
    "command",
    [
        "Get-Process | Stop-Process",
        "Remove-Item C:\\temp\\x.txt",
        "Set-Service Spooler -StartupType Disabled",
    ],
)
def test_mutating_commands_never_reach_provider(monkeypatch, command):
    c = connector(monkeypatch)

    with pytest.raises(PermissionError):
        c.execute(request(command))

    assert c._transport.calls == []


def test_sensitive_read_never_reaches_provider(monkeypatch):
    c = connector(monkeypatch)

    with pytest.raises(PermissionError):
        c.execute(request(r"Get-Item HKLM:\SAM"))

    assert c._transport.calls == []


def test_uncertain_command_never_reaches_provider(monkeypatch):
    c = connector(monkeypatch)

    with pytest.raises(PermissionError):
        c.execute(request("Watch-Thing"))

    assert c._transport.calls == []


def test_classifier_and_transport_share_same_boundary(monkeypatch):
    c = connector(monkeypatch)
    command = "Test-NetConnection example.com -Port 443"
    expected = DattoRmmReadOnlyPowerShellPolicy().prepare_command(
        device_uid="device-1",
        command=command,
    )

    result = c.execute(request(command))

    assert expected.active_probe is True
    assert result.data["active_probe"] is True


def test_output_is_bounded(monkeypatch):
    c = connector(monkeypatch)

    payload = [
        {
            "componentUid": DATTO_AD_HOC_POWERSHELL_UID,
            "stdData": "A" * 60000,
        }
    ]
    text, bounded, matches = c._bounded_stream(payload, stream="stdout")

    assert len(text) == c.maximum_output_chars
    assert bounded is True
    assert matches == 1
