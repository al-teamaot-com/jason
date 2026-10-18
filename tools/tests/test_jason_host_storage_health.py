"""No-write host capacity monitoring and guarded incident regression tests."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import jason_host_storage_health as storage
import issue_resolution_engine as resolver
import jason_self_heal_watchdog as watchdog


def counters(*, used: int, available: int, reserved: int = 0,
             inodes_used: int = 50, inodes_total: int = 100):
    # One block is a GiB for readable fixture values.
    total = used + available + reserved
    return SimpleNamespace(
        f_frsize=storage.GIB, f_bsize=storage.GIB,
        f_blocks=total, f_bfree=available + reserved, f_bavail=available,
        f_files=inodes_total, f_ffree=inodes_total - inodes_used,
    )


def policy(tmp_path):
    data = {
        "schema_version": "1.0", "monitoring_mode": "read_only",
        "remediation": "ticket_or_owner_approval_required",
        "warning_used_percent": 80, "critical_used_percent": 90,
        "warning_available_gib": 30, "critical_available_gib": 15,
        "warning_inode_used_percent": 85, "critical_inode_used_percent": 95,
        "mounts": [
            {"id": "root", "path": "/", "must_be_mount": True},
            {"id": "archive", "path": "/srv/jason/archive", "must_be_mount": True},
        ],
    }
    path = tmp_path / "host-storage-capacity-v1.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def check(tmp_path, root, archive=None, *, mounted_archive=True):
    path = policy(tmp_path)
    archive = archive or counters(used=11, available=222, reserved=1)
    def source(mount):
        if mount == "/":
            return root
        assert mount == "/srv/jason/archive"
        return archive
    return storage.storage_capacity_failures(
        policy_path=path, statvfs=source,
        ismount=lambda m: m == "/" or mounted_archive,
    )


def test_current_production_root_is_critical_archive_is_healthy(tmp_path):
    issues, evidence = check(tmp_path, counters(used=201, available=21, reserved=8))
    assert issues == ["host_storage_capacity_critical:root"]
    assert evidence["status"] == "degraded"
    assert evidence["mounts"]["root"]["used_percent"] > 90
    assert evidence["mounts"]["root"]["available_gib"] == 21
    assert evidence["mounts"]["archive"]["state"] == "healthy"
    assert evidence["mounts"]["archive"]["path"] == "/srv/jason/archive"


def test_disk_early_warning_before_critical(tmp_path):
    issues, evidence = check(tmp_path, counters(used=79, available=31, reserved=4))
    assert issues == []  # <80% and >30GiB free: no false positive
    issues, evidence = check(tmp_path, counters(used=80, available=20, reserved=0))
    assert issues == ["host_storage_capacity_warning:root"]
    assert evidence["mounts"]["root"]["state"] == "warning"


def test_absolute_free_space_threshold_catches_small_disks(tmp_path):
    issues, evidence = check(tmp_path, counters(used=60, available=10))
    assert issues == ["host_storage_capacity_critical:root"]
    assert "allocatable_free_bytes" in evidence["mounts"]["root"]["reasons"]


def test_inode_exhaustion_triggers_even_with_free_blocks(tmp_path):
    issues, evidence = check(tmp_path, counters(used=10, available=200, inodes_used=96))
    assert issues == ["host_storage_capacity_critical:root"]
    assert "inode_exhaustion" in evidence["mounts"]["root"]["reasons"]


def test_missing_archive_mount_fails_closed_and_never_probes_root_as_archive(tmp_path):
    issues, evidence = check(tmp_path, counters(used=10, available=100), mounted_archive=False)
    assert issues == ["host_storage_mount_missing:archive"]
    assert evidence["mounts"]["archive"]["state"] == "unknown"
    assert evidence["mounts"]["archive"]["reason"] == "required_mount_not_mounted"


def test_invalid_or_unreadable_counter_does_not_silently_pass(tmp_path):
    issues, evidence = storage.storage_capacity_failures(
        policy_path=policy(tmp_path),
        statvfs=lambda mount: (_ for _ in ()).throw(OSError("inaccessible")),
        ismount=lambda mount: True,
    )
    assert issues == ["host_storage_probe_unavailable:archive", "host_storage_probe_unavailable:root"]
    assert evidence["status"] == "degraded"


def test_malformed_policy_fails_closed_not_optional(tmp_path):
    path = policy(tmp_path)
    body = json.loads(path.read_text())
    body["monitoring_mode"] = "auto_prune"
    path.write_text(json.dumps(body))
    failures, evidence = storage.storage_capacity_failures(policy_path=path)
    assert failures == ["host_storage_monitor_unavailable:policy"]
    body["monitoring_mode"] = "read_only"
    body["mounts"][1]["path"] = "/"
    path.write_text(json.dumps(body))
    failures, evidence = storage.storage_capacity_failures(policy_path=path)
    assert failures == ["host_storage_monitor_unavailable:policy"]


def test_correlates_capacity_with_own_durable_incident_and_no_autocleanup(tmp_path):
    issues, evidence = check(tmp_path, counters(used=201, available=21, reserved=8))
    incidents = resolver.correlate_failures(issues)
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["family"] == "host_storage_capacity"
    assert incident["repair"]["automatic_execution"] is False
    assert incident["repair"]["requires_owner_action"] is True
    assert incident["repair"]["level"] == 3
    assert "statvfs" in ";".join(incident["verification_contract"]["required_checks"])
    assert resolver.incident_fingerprint("host_storage_capacity", issues) == incident["fingerprint"]
    assert watchdog.bounded_recovery(issues) == []
    recorded = resolver.update_recurrence_memory(tmp_path / "memory.json", incidents)
    assert recorded[0]["priority"] == "P0"
    # A second report doesn't create a new item and doesn't authorize deletion.
    again = resolver.update_recurrence_memory(tmp_path / "memory.json", incidents)
    assert again[0]["fingerprint"] == recorded[0]["fingerprint"]
    assert again[0]["repair"]["automatic_execution"] is False
    assert again[0]["occurrence_count"] == 1


def test_warning_is_p1_even_when_same_family_recurs(tmp_path):
    incidents = resolver.correlate_failures(["host_storage_capacity_warning:root"])
    memory = tmp_path / "memory.json"
    resolver.update_recurrence_memory(memory, incidents)
    resolver.update_recurrence_memory(memory, [])
    again = resolver.update_recurrence_memory(memory, incidents)
    assert again[0]["priority"] == "P1"
    assert again[0]["recurring"] is True


def test_storage_read_is_in_existing_selfheal_detector(monkeypatch, tmp_path):
    # All other probes are stubbed; test integration only without provider calls.
    monkeypatch.setattr(watchdog, "container_running", lambda name: True)
    monkeypatch.setattr(watchdog, "mcp_status_probe", lambda: (True, "ok"))
    monkeypatch.setattr(watchdog, "production_convergence_failures", lambda: ([], {}))
    monkeypatch.setattr(watchdog, "failed_jason_user_units", lambda: [])
    monkeypatch.setattr(watchdog, "operational_outcome_contract_failures", lambda p: ([], []))
    monkeypatch.setattr(watchdog, "stale_operational_work_failures", lambda: ([], []))
    monkeypatch.setattr(watchdog, "autonomy_admission_failures", lambda: ([], {}))
    monkeypatch.setattr(watchdog, "autonomy_behavior_anomalies", lambda: ([], {}))
    monkeypatch.setattr(watchdog, "provider_canary_monitoring_failures", lambda: ([], {"fresh": False}))
    monkeypatch.setattr(watchdog, "health_metrics", lambda: ({}, None))
    monkeypatch.setattr(
        watchdog, "storage_capacity_failures",
        lambda: (["host_storage_capacity_critical:root"], {"mounts": {"root": {"state": "critical"}}}),
    )
    failures, evidence = watchdog.detect(tmp_path)
    assert failures == ["host_storage_capacity_critical:root"]
    assert evidence["host_storage_capacity"]["mounts"]["root"]["state"] == "critical"


def test_storage_incident_is_persisted_without_waking_autonomous_repair(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        watchdog, "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    incident = resolver.correlate_failures(["host_storage_capacity_critical:root"])[0]
    incident["priority"] = "P0"
    path = watchdog.queue_resolution_incident(
        tmp_path, incident, {"host_storage_capacity": {"mounts": {"root": {"available_gib": 20}}}},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["family"] == "host_storage_capacity"
    assert payload["priority"] == "P0"
    assert payload["requires_owner_action"] is True
    assert payload["repair_level"] == 3
    assert calls == []  # no autonomous repair worker, restart or Docker prune


def test_storage_escalation_requests_exact_scope_and_keeps_provider_permissions(tmp_path):
    incident = resolver.correlate_failures(["host_storage_capacity_critical:root"])[0]
    path = watchdog.write_incident_escalation(
        tmp_path, incident=incident, attempts=2, actions=[],
    )
    body = json.loads(path.read_text(encoding="utf-8"))
    assert "approve bounded" in body["owner_action"]
    assert "Docker volumes" in body["owner_action"]
    assert "rollback images" in body["owner_action"]
    assert body["family"] == "host_storage_capacity"
    assert body["state"] == "owner_action_required"
