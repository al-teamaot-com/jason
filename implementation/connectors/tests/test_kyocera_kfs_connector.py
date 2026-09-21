from __future__ import annotations

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.kyocera_kfs import KFS_DEFAULT_API_URL, KyoceraKfsConnector


class FakeSecrets:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return dict(self.values)


class FakeTransport:
    def request(self, **kwargs):
        raise AssertionError("KFS session connector must not use the stateless transport")


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeSessionClient:
    calls = []

    def __init__(self, credentials):
        self.credentials = credentials

    def call(self, path, body):
        self.calls.append((path, dict(body)))
        if path == "/KFS/GroupList":
            return {
                "grpTree": {"topGroups": ["root-1"]},
                "groups": [{"groupId": "root-1"}],
                "status": {"code": 200},
            }
        if path == "/KFS/DeviceList":
            return {
                "devices": [
                    {
                        "groupId": "root-1",
                        "deviceId": "dev-1",
                        "attributes": {
                            "serialNumber": "ABC123",
                            "modelName": "TASKalfa 3554ci",
                            "assetNumber": "AOT-9001",
                        },
                        "counters": {"total": 12345},
                    }
                ],
                "status": {"code": 200},
            }
        if path == "/KFS/Device":
            return {
                "devices": [{"deviceId": body["device"], "counters": {"total": 12345}}],
                "status": {"code": 200},
            }
        if path == "/KFS/DeviceLogList":
            return {
                "devices": [{"deviceId": "dev-1", "logs": [{"detail": "string-errorcode_all"}]}],
                "status": {"code": 200},
            }
        return {"status": {"code": 200}}


def credentials():
    return {
        "api_url": KFS_DEFAULT_API_URL,
        "request_from": "REQUEST-FROM",
        "request_to": "KFS_US",
        "authorization": "Basic opaque",
        "kfs_username": "apiuser",
        "kfs_password": "secret",
    }


def context(capability, mode="observe"):
    return ConnectorContext(
        correlation_id="corr-kfs-001",
        principal_id="tech-al",
        organization_id="aot",
        client_id="client-1",
        capability=capability,
        mode=mode,
    )


def build(values=None):
    FakeSessionClient.calls.clear()
    secrets = FakeSecrets(values or credentials())
    audit = FakeAudit()
    connector = KyoceraKfsConnector(
        secrets,
        FakeTransport(),
        audit,
        client_factory=FakeSessionClient,
    )
    return connector, secrets, audit


def test_device_search_uses_group_list_and_root_scope():
    connector, secrets, _ = build()
    result = connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.device.search"),
            {"serial_number": "ABC123"},
        )
    )
    assert result.data["matched_count"] == 1
    assert result.data["devices"][0]["deviceId"] == "dev-1"
    assert FakeSessionClient.calls[0][0] == "/KFS/GroupList"
    path, body = FakeSessionClient.calls[1]
    assert path == "/KFS/DeviceList"
    assert body["scope"] == 1
    assert body["deviceAttrIds"] == ["all"]
    assert secrets.calls == ["kyocera_kfs.readonly"]


def test_meter_read_uses_device_endpoint_and_all_counters():
    connector, _, audit = build()
    result = connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.meters.get"),
            {"device_id": "dev-1"},
        )
    )
    assert result.data["devices"][0]["counters"]["total"] == 12345
    path, body = FakeSessionClient.calls[-1]
    assert path == "/KFS/Device"
    assert body["BODID"] == "Global_KFS_Pull_Device"
    assert body["counters"] == ["all"]
    assert audit.events[0][1]["operation"] == "meters_get"


def test_alert_search_uses_device_log_list_for_group():
    connector, _, _ = build()
    connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.alerts.list"),
            {"group_id": "root-1"},
        )
    )
    path, body = FakeSessionClient.calls[-1]
    assert path == "/KFS/DeviceLogList"
    assert body["groupTreeState"] == 3


def test_missing_manager_login_fails_closed():
    values = credentials()
    del values["kfs_password"]
    connector, _, _ = build(values)
    with pytest.raises(ConnectorConfigurationError, match="kfs_password"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get"),
                {"device_id": "dev-1"},
            )
        )


def test_non_observe_mode_is_rejected_before_provider_call():
    connector, _, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="read-only"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get", mode="execute"),
                {"device_id": "dev-1"},
            )
        )
    assert FakeSessionClient.calls == []
