from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.core.mutations import ApprovalGrant
from connectors.kfs.connector import KfsConnector
from connectors.kfs.mutations import KfsMutationConnector


class MemoryAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context, details))


class MemorySecrets:
    def resolve(self, logical_name, context):
        assert logical_name == "kfs.runtime"
        return {
            "request_from": "AOT",
            "request_to": "KFS_US",
            "manager_id": "apiuser",
            "manager_password": "secret",
            "authorization": "base64-token",
        }


class FakeKfsClient:
    calls = []

    def __init__(self, credentials, *, base_url, api_version):
        assert base_url == "https://api.kyods.com"
        assert api_version == 6
        assert credentials["manager_id"] == "apiuser"

    def call(self, path, body, *, min_api_version=1):
        self.calls.append((path, body, min_api_version))
        return {
            "status": {
                "code": 200,
                "messageResource": "string-serverres-success",
            }
        }


def context(capability, mode="observe"):
    return ConnectorContext(
        correlation_id="corr-kfs-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        capability=capability,
        mode=mode,
    )


def test_group_list_uses_separate_gateway_and_manager_credentials():
    FakeKfsClient.calls.clear()
    connector = KfsConnector(
        MemorySecrets(),
        MemoryAudit(),
        base_url="https://api.kyods.com",
        api_version=6,
        client_factory=FakeKfsClient,
    )
    result = connector.execute(
        ConnectorRequest(
            context("kfs.group.list"),
            {},
        )
    )
    assert result.provider == "kfs"
    path, body, minimum = FakeKfsClient.calls[-1]
    assert path == "/KFS/GroupList"
    assert body["BODID"] == "Global_KFS_Pull_GroupList"
    assert body["RequestTo"] == "KFS_US"
    assert body["groupAttrIds"] == ["all"]
    assert minimum == 1


def test_device_list_requires_group_and_can_request_all_data():
    connector = KfsConnector(
        MemorySecrets(),
        MemoryAudit(),
        base_url="https://api.kyods.com",
        client_factory=FakeKfsClient,
    )
    with pytest.raises(ValueError, match="group_id"):
        connector.execute(
            ConnectorRequest(
                context("kfs.device.list"),
                {},
            )
        )

    FakeKfsClient.calls.clear()
    connector.execute(
        ConnectorRequest(
            context("kfs.device.list"),
            {"group_id": "123"},
        )
    )
    _, body, _ = FakeKfsClient.calls[-1]
    assert body["groupId"] == "123"
    assert body["deviceAttrIds"] == ["all"]
    assert body["counters"] == ["all"]


def test_change_status_is_not_available_as_observe_read():
    connector = KfsConnector(
        MemorySecrets(),
        MemoryAudit(),
        base_url="https://api.kyods.com",
        client_factory=FakeKfsClient,
    )
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(
            ConnectorRequest(
                context("kfs.device.management_status.change"),
                {"device_ids": ["device-1"], "target_status": 2},
            )
        )


def test_change_status_proposal_is_governed_and_termination_warns():
    audit = MemoryAudit()
    connector = KfsMutationConnector(audit=audit)
    result = connector.execute(
        ConnectorRequest(
            context(
                "kfs.device.management_status.change",
                mode="propose",
            ),
            {
                "device_ids": ["device-1"],
                "target_status": 5,
                "reason": "Retire copier from KFS management",
            },
        )
    )
    assert result.data["status"] == "proposed"
    assert result.data["plan"]["proposed_changes"]["target_status"] == 5
    assert result.data["plan"]["proposed_changes"]["target_status_name"] == "terminated"
    assert result.warnings
    assert any(
        event[0] == "connector.mutation.planned"
        for event in audit.events
    )


def test_change_status_execute_requires_approval_and_idempotency():
    connector = KfsMutationConnector(audit=MemoryAudit())
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(
            ConnectorRequest(
                context(
                    "kfs.device.management_status.change",
                    mode="execute",
                ),
                {
                    "device_ids": ["device-1"],
                    "target_status": 2,
                    "reason": "Move copier to unmanaged",
                },
            )
        )
