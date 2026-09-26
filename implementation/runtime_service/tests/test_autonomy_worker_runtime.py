from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from autonomous_remediation.autonomous_queue_worker import QueueCandidate
from jason_runtime.autonomy_worker_runtime import (
    OperationalAutonomyMaintenance,
    SQLiteOperationalWorkStore,
)


class PromotionStore:
    def __init__(self, promoted=("datto_edr_av",)):
        self.promoted = set(promoted)

    def find_scope_approved(self, **kwargs):
        if kwargs.get("playbook_id") not in self.promoted:
            return None
        return SimpleNamespace(
            approval_id="approval-owner",
            allowed_capabilities=(
                "automation.component.execute",
                "service.ticket.note.create",
                "service.ticket.update",
            ),
        )


class QueueSource:
    def __init__(self, candidate):
        self.candidate = candidate

    def reconcile_candidates(self):
        return (self.candidate,)


class Reads:
    def __init__(self):
        self.job_status = "completed"

    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "item": {
                            "id": 1583,
                            "companyID": 507,
                            "isActive": True,
                            "referenceNumber": "device-uid-1",
                            "referenceTitle": "PC-1",
                        }
                    }
                },
            }
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-1",
                        "hostname": "PC-1",
                        "online": True,
                    }
                },
            }
        if capability == "automation.job.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "job": {
                        "resource_id": arguments["resource_id"],
                        "status": self.job_status,
                    }
                },
            }
        if capability == "automation.job.output.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_id": arguments["resource_id"],
                    "outputs": [
                        {
                            "component_uid": arguments["component_uid"],
                            "stream": "stdout",
                            "text": "Status=Healthy\nEDRVersion=3.17.1",
                        }
                    ],
                },
            }
        raise AssertionError(capability)


class Actions:
    def __init__(self):
        self.calls = []
        self.jobs = 0

    def execute(self, scope, capability, arguments):
        self.calls.append((scope.playbook_id, capability, arguments))
        if capability == "automation.component.execute":
            self.jobs += 1
            return {
                "data": {
                    "job_uid": f"job-{self.jobs}",
                    "job_status": "active",
                }
            }
        return {}


def candidate(title="[Monitor] Antivirus status issue"):
    return QueueCandidate(
        resource_id="140933",
        priority=100,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140933,
            "ticketNumber": "T20260925.9999",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_health_only_edr_ticket_is_admitted_but_threat_ticket_is_not():
    assert OperationalAutonomyMaintenance._is_health_only_edr_ticket(
        candidate().context
    )
    assert not OperationalAutonomyMaintenance._is_health_only_edr_ticket(
        candidate("Security Threat detected - Antivirus status").context
    )


def test_verified_healthy_ticket_is_claimed_documented_and_completed(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140933)
    assert first is not None
    assert first.phase == "health_wait"
    assert first.job_uid == "job-1"

    worker.tick()
    final = store.get(140933)
    assert final is not None
    assert final.phase == "complete"
    assert final.repair_attempts == 0

    ticket_updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert ticket_updates[0] == {
        "id": 140933,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }
    assert ticket_updates[-1] == {"id": 140933, "status": "Complete"}

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"].startswith(
        "Check Datto EDR/AV Status"
    )

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "Status=Healthy" in note_calls[0]["description"]
    store.close()


def test_nonhealthy_health_check_runs_one_repair_then_verifies(tmp_path: Path):
    class RepairReads(Reads):
        def __init__(self):
            super().__init__()
            self.output_reads = 0

        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                self.output_reads += 1
                text = (
                    "Status=IssuesFound\nAVHealthy=False"
                    if self.output_reads == 1
                    else "Status=Healthy\nAVHealthy=True"
                )
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": text,
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    reads = RepairReads()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    clock = iter((0.0, 31.0, 62.0, 93.0, 124.0)).__next__
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        interval_seconds=30,
        monotonic=clock,
    )

    worker.tick()  # claim + health dispatch
    worker.tick()  # nonhealthy -> repair_dispatch
    assert store.get(140933).phase == "repair_dispatch"
    worker.tick()  # repair dispatch
    assert store.get(140933).phase == "repair_wait"
    worker.tick()  # repair completed -> verify_dispatch
    assert store.get(140933).phase == "verify_dispatch"
    worker.tick()  # verify dispatch
    assert store.get(140933).phase == "verify_wait"

    component_names = [
        args["component_name"]
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_names == [
        "Check Datto EDR/AV Status AOT Ver 12122025-1",
        "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
        "Check Datto EDR/AV Status AOT Ver 12122025-1",
    ]
    assert store.get(140933).repair_attempts == 1
    store.close()


def test_worker_accepts_provider_native_datto_device_identity(tmp_path: Path):
    class RawEndpointReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "uid": "device-uid-1",
                            "hostname": "PC-1",
                            "online": True,
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=RawEndpointReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.phase == "health_wait"
    assert work.device_uid == "device-uid-1"
    assert work.hostname == "PC-1"
    store.close()


def dns_candidate(title="DNS Agent service isStopped for PC-1"):
    return QueueCandidate(
        resource_id="140944",
        priority=90,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140944,
            "ticketNumber": "T20260926.0001",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_dns_ticket_requires_dns_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(dns_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140944) is None
    assert actions.calls == []
    store.close()


def test_dns_ticket_runs_standing_safe_diagnostic_then_escalates(tmp_path: Path):
    class DnsReads(Reads):
        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": (
                                    "INCIDENT_CLASSIFICATION=agent_corrupt_or_partial\n"
                                    "FILTERING_SERVICE=Stopped\n"
                                    "SERVICE_MANAGER=Running\n"
                                    "DNS_RESOLUTION=Success"
                                ),
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(dns_candidate()),
        reads=DnsReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av", "dns_agent_diagnostic")),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140944)
    assert first is not None
    assert first.playbook_id == "dns_agent_diagnostic"
    assert first.phase == "dns_diagnostic_wait"

    worker.tick()
    final = store.get(140944)
    assert final is not None
    assert final.phase == "escalated"
    assert "remediation branch requires separate accepted authority" in final.last_reason

    component_calls = [
        args
        for playbook_id, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == (
        "DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026"
    )
    assert component_calls[0]["component_uid"] == (
        "c3340a58-48d5-457b-bc30-5fd79e5ad8b1"
    )

    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [{
        "id": 140944,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }]

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "No service restart" in note_calls[0]["description"]
    store.close()


def security_candidate(title="SET-03 - Windows Security Log unreadable"):
    return QueueCandidate(
        resource_id="140955",
        priority=95,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140955,
            "ticketNumber": "T20260926.0002",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_security_log_ticket_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av", "dns_agent_diagnostic")),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140955) is None
    assert actions.calls == []
    store.close()


def test_security_log_healthy_quick_test_documents_and_stops_before_alert_cleanup(
    tmp_path: Path,
):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "dns_agent_diagnostic", "security_log_self_heal")
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140955)
    assert first is not None
    assert first.playbook_id == "security_log_self_heal"
    assert first.phase == "security_quick_wait"

    worker.tick()
    final = store.get(140955)
    assert final is not None
    assert final.phase == "escalated"
    assert final.repair_attempts == 0
    assert "cleanup remains separately gated" in final.last_reason

    component_calls = [
        args
        for playbook_id, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == (
        "Security Log Quick Test [WIN] AOT Ver 12012025-1"
    )

    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [{
        "id": 140955,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }]

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "No repair was required" in note_calls[0]["description"]
    store.close()


def test_security_log_unhealthy_runs_one_self_heal_then_verifies(tmp_path: Path):
    class SecurityReads(Reads):
        def __init__(self):
            super().__init__()
            self.output_reads = 0

        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                self.output_reads += 1
                text = (
                    "Status=Unhealthy\nSecurityLogReadable=False"
                    if self.output_reads == 1
                    else "Status=Healthy\nSecurityLogReadable=True"
                )
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": text,
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    reads = SecurityReads()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "dns_agent_diagnostic", "security_log_self_heal")
        ),
        interval_seconds=30,
        monotonic=iter((0.0, 31.0, 62.0, 93.0, 124.0, 155.0)).__next__,
    )

    worker.tick()
    worker.tick()
    assert store.get(140955).phase == "security_repair_dispatch"
    worker.tick()
    assert store.get(140955).phase == "security_repair_wait"
    worker.tick()
    assert store.get(140955).phase == "security_verify_dispatch"
    worker.tick()
    assert store.get(140955).phase == "security_verify_wait"
    worker.tick()

    final = store.get(140955)
    assert final.phase == "escalated"
    assert final.repair_attempts == 1
    assert "cleanup remains separately gated" in final.last_reason

    component_names = [
        args["component_name"]
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_names == [
        "Security Log Quick Test [WIN] AOT Ver 12012025-1",
        "Security Log Self-Heal [WIN] AOT Ver 11262025-2",
        "Security Log Quick Test [WIN] AOT Ver 12012025-1",
    ]
    store.close()
