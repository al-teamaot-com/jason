from datetime import datetime, timedelta, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.datto_edr_scan_execution import (
    DATTO_EDR_PROVIDER_CAPABILITY,
    DattoEdrScanConnector,
    DattoEdrScanRateLimitedError,
    DattoEdrScanVerificationError,
)

RESOURCE_ID = "69571572-83f7-1e33-9cdf-01717d4e74a4"
AGENT_ID = "0cf9b495-879b-4b6c-8c60-ac229e01d136"


class Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == "datto_edr.readonly"
        return {
            "api_url": "https://tenant.example/api",
            "api_token": "synthetic-token",
        }


class Audit:
    def record(self, *args):
        pass


class Transport:
    def __init__(self, agent):
        self.agent = dict(agent)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["method"] == "GET":
            return [dict(self.agent)]
        if kwargs["method"] == "POST":
            return {"id": "task-123"}
        raise AssertionError(kwargs["method"])


def request(scan_type="quick"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability=DATTO_EDR_PROVIDER_CAPABILITY,
            mode="execute",
        ),
        arguments={
            "resource_id": RESOURCE_ID,
            "agent_id": AGENT_ID,
            "scan_type": scan_type,
        },
    )


def healthy_agent(**overrides):
    data = {
        "id": AGENT_ID,
        "deviceId": RESOURCE_ID,
        "hasAvLicense": True,
        "dattoAvEnabled": True,
        "scanStatus": "completed",
        "lastAvScanTime": (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat(),
    }
    data.update(overrides)
    return data


def test_quick_scan_uses_exact_datto_payload():
    transport = Transport(healthy_agent())
    connector = DattoEdrScanConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(request("quick"))

    assert [c["method"] for c in transport.calls] == ["GET", "POST"]
    payload = transport.calls[1]["json"]
    assert payload["where"] == {"and": [{"id": [AGENT_ID]}]}
    assert payload["taskName"] == "Scan - AV Quick"
    assert payload["options"]["diskScan"] is True
    assert payload["options"]["quickScan"] is True
    assert payload["options"]["fullScan"] is False
    assert payload["options"]["forensicScan"] is False
    assert result.data["task_id"] == "task-123"


def test_full_scan_is_mutually_exclusive():
    transport = Transport(healthy_agent())
    connector = DattoEdrScanConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )
    connector.execute(request("full"))
    payload = transport.calls[1]["json"]
    assert payload["taskName"] == "Scan - AV Full"
    assert payload["options"]["quickScan"] is False
    assert payload["options"]["fullScan"] is True


def test_scan_fails_closed_on_device_mismatch():
    transport = Transport(healthy_agent(deviceId="different"))
    connector = DattoEdrScanConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )
    with pytest.raises(DattoEdrScanVerificationError, match="device UID"):
        connector.execute(request())
    assert [c["method"] for c in transport.calls] == ["GET"]


def test_scan_enforces_one_hour_guard():
    transport = Transport(
        healthy_agent(
            lastAvScanTime=(
                datetime.now(timezone.utc) - timedelta(minutes=20)
            ).isoformat()
        )
    )
    connector = DattoEdrScanConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )
    with pytest.raises(DattoEdrScanRateLimitedError):
        connector.execute(request())
    assert [c["method"] for c in transport.calls] == ["GET"]


def test_scan_refuses_when_provider_reports_in_progress():
    transport = Transport(healthy_agent(scanStatus="in-progress"))
    connector = DattoEdrScanConnector(
        secrets=Secrets(),
        transport=transport,
        audit=Audit(),
    )
    with pytest.raises(DattoEdrScanVerificationError, match="already in progress"):
        connector.execute(request())
    assert [c["method"] for c in transport.calls] == ["GET"]
