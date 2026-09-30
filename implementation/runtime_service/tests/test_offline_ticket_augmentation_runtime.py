from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from autonomous_remediation.autonomous_queue_worker import QueueCandidate
from jason_runtime.autonomy_worker_runtime import (
    OperationalAutonomyMaintenance,
    SQLiteOperationalWorkStore,
)


class QueueSource:
    def __init__(self, candidate):
        self.candidate = candidate

    def reconcile_candidates(self):
        return (self.candidate,)


class PromotionStore:
    def __init__(self, promoted=True):
        self.promoted = promoted

    def find_scope_approved(self, **kwargs):
        if (
            not self.promoted
            or kwargs.get("playbook_id")
            != "offline_ticket_context_augmentation"
        ):
            return None
        return SimpleNamespace(
            approval_id="owner-augmentation-approval",
            allowed_capabilities=("service.ticket.note.create",),
        )


class Reads:
    def __init__(self, *, server_online=True, include_second_offline=False):
        self.server_online = server_online
        self.include_second_offline = include_second_offline
        self.powershell_reads = 0

    @staticmethod
    def success(data):
        return {"status": "succeeded", "evidence": {"data": data}}

    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return self.success(
                {
                    "item": {
                        "id": 1583,
                        "companyID": 507,
                        "isActive": True,
                        "referenceNumber": "target-uid",
                        "referenceTitle": "PC-1",
                    }
                }
            )
        if capability == "endpoint.device.read":
            uid = arguments["resource_id"]
            if uid == "target-uid":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "target-uid",
                            "hostname": "PC-1",
                            "online": False,
                            "site": "Riggins",
                            "device_type": "Desktop",
                        }
                    },
                }
            if uid == "server-uid":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "server-uid",
                            "hostname": "RIG-SRV",
                            "online": self.server_online,
                            "site": "Riggins",
                            "device_type": "Server",
                            "operatingSystem": "Microsoft Windows Server 2022",
                        }
                    },
                }
            if uid == "pc2-uid":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "pc2-uid",
                            "hostname": "RIG-PC-2",
                            "online": False,
                            "site": "Riggins",
                            "device_type": "Desktop",
                        }
                    },
                }
            raise AssertionError(uid)
        if capability == "endpoint.device.search":
            peers = [
                {
                    "resource_id": "server-uid",
                    "hostname": "RIG-SRV",
                    "online": self.server_online,
                    "site": "Riggins",
                    "device_type": "Server",
                    "operatingSystem": "Microsoft Windows Server 2022",
                },
            ]
            if self.include_second_offline:
                peers.append(
                    {
                        "resource_id": "pc2-uid",
                        "hostname": "RIG-PC-2",
                        "online": False,
                        "site": "Riggins",
                        "device_type": "Desktop",
                    }
                )
            return self.success({"resource_matches": peers})
        if capability == "backup.endpoint.asset.search":
            return self.success(
                {
                    "items": [
                        {
                            "id": "asset-1",
                            "name": "PC-1",
                            "status": "offline",
                        }
                    ]
                }
            )
        if capability == "endpoint.powershell.read":
            self.powershell_reads += 1
            if not self.server_online:
                raise RuntimeError("server unavailable")
            return self.success(
                {
                    "stdout": (
                        "InterfaceAlias : Ethernet\n"
                        "IPv4Address    : 192.168.1.2\n"
                        "IPv4DefaultGateway : 192.168.1.1"
                    ),
                    "stderr": "",
                    "exit_code": 0,
                }
            )
        raise AssertionError(capability)


class Actions:
    def __init__(self):
        self.calls = []

    def execute(self, scope, capability, arguments):
        self.calls.append((scope.playbook_id, capability, arguments))
        return {
            "data": {
                "jasonVerification": {
                    "readbackVerified": True,
                }
            }
        }


def offline_candidate():
    return QueueCandidate(
        resource_id="140933",
        priority=100,
        source_queue="Help Desk I",
        owned_by_jason=False,
        urgent=False,
        source_version="2026-09-30T17:00:00Z",
        context={
            "id": 140933,
            "ticketNumber": "T20260930.9999",
            "title": "[Monitor] Server is offline - PC-1",
            "description": "Managed endpoint stopped checking in.",
            "companyID": 507,
            "configurationItemID": 1583,
            "_jason_source_status_label": "New",
            "_jason_assigned_elsewhere": True,
        },
    )


def maintenance(tmp_path: Path, *, reads, actions, promoted=True):
    return OperationalAutonomyMaintenance(
        queue_source=QueueSource(offline_candidate()),
        reads=reads,
        actions=actions,
        store=SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3"),
        promotion_store=PromotionStore(promoted=promoted),
        interval_seconds=60,
    )


def test_assigned_offline_ticket_gets_context_without_ownership_change(tmp_path):
    reads = Reads(server_online=True)
    actions = Actions()
    worker = maintenance(tmp_path, reads=reads, actions=actions)

    worker.tick()

    note_calls = [call for call in actions.calls if call[1] == "service.ticket.note.create"]
    assert len(note_calls) == 1
    assert note_calls[0][0] == "offline_ticket_context_augmentation"
    note = note_calls[0][2]["payload"]["description"]
    assert "STATUS: Site confirmed up." in note
    assert "LiveOnSiteWitness=RIG-SRV" in note
    assert "has not taken ownership" in note
    assert not [call for call in actions.calls if call[1] == "service.ticket.update"]
    assert not [call for call in actions.calls if call[1] == "automation.component.execute"]


def test_multiple_fixed_offline_peers_yield_site_likely_down(tmp_path):
    reads = Reads(server_online=False, include_second_offline=True)
    actions = Actions()
    worker = maintenance(tmp_path, reads=reads, actions=actions)

    worker.tick()

    note = next(
        call[2]["payload"]["description"]
        for call in actions.calls
        if call[1] == "service.ticket.note.create"
    )
    assert "STATUS: Site likely down." in note
    assert "OfflineFixedPeers=RIG-PC-2,RIG-SRV" in note


def test_augmentation_is_durable_and_not_repeated_every_worker_minute(tmp_path):
    reads = Reads(server_online=True)
    actions = Actions()
    now = [0.0]

    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(offline_candidate()),
        reads=reads,
        actions=actions,
        store=SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3"),
        promotion_store=PromotionStore(promoted=True),
        interval_seconds=60,
        monotonic=lambda: now[0],
    )

    worker.tick()
    now[0] = 61.0
    worker.tick()

    note_calls = [call for call in actions.calls if call[1] == "service.ticket.note.create"]
    assert len(note_calls) == 1
    assert reads.powershell_reads == 1


def test_without_exact_owner_promotion_augmentation_does_not_write(tmp_path):
    reads = Reads(server_online=True)
    actions = Actions()
    worker = maintenance(
        tmp_path,
        reads=reads,
        actions=actions,
        promoted=False,
    )

    worker.tick()

    assert not [call for call in actions.calls if call[1] == "service.ticket.note.create"]
    assert reads.powershell_reads == 0
