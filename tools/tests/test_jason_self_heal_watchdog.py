from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "jason_self_heal_watchdog",
    ROOT / "tools" / "jason_self_heal_watchdog.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_fingerprint_is_order_independent():
    assert module.fingerprint(["b", "a"]) == module.fingerprint(["a", "b"])


def test_bounded_recovery_restarts_only_failed_local_surface(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "container_running", lambda name: True)

    actions = module.bounded_recovery(["mcp_status_functional_failure"])

    assert calls == [["docker", "restart", "-t", "10", "jason-mcp-pilot"]]
    assert "docker restart jason-mcp-pilot" in actions[0]


def test_queue_support_repair_persists_stable_auto_support_item(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    path = module.queue_support_repair(
        tmp_path,
        "abcdef1234567890",
        ["provider_canary_failure"],
        {"sample": True},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["support_item"] == "SUPPORT-AUTO-ABCDEF123456"
    assert payload["state"] == "repair_required"
    assert calls[-1] == ["systemctl", "--user", "start", "--no-block", "jason-support-repair-worker.service"]


def test_escalation_payload_requires_owner_action(tmp_path):
    path = module.write_escalation(
        tmp_path,
        fp="abc123",
        failures=["mcp_status_functional_failure"],
        attempts=2,
        actions=["docker restart jason-mcp-pilot: rc=0"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["state"] == "owner_action_required"
    assert payload["attempts"] == 2
    assert "Owner action" not in payload["owner_action"]
    assert payload["owner_action"]


def test_outcome_contract_overdue_is_detected(tmp_path):
    contracts = tmp_path / module.OUTCOME_CONTRACT_DIRNAME
    contracts.mkdir(parents=True)
    payload = {
        "contract_id": "notify-123",
        "function": "client_notification",
        "state": "pending",
        "verify_by": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "evidence_summary": "ticket note created; NotificationHistory not yet verified",
    }
    (contracts / "notify-123.json").write_text(json.dumps(payload), encoding="utf-8")

    failures, evidence = module.operational_outcome_contract_failures(tmp_path)

    assert failures == [
        "outcome_contract_overdue:client_notification:notify-123"
    ]
    assert evidence[0]["contract_id"] == "notify-123"
    assert evidence[0]["state"] == "pending"


def test_verified_outcome_contract_is_healthy(tmp_path):
    contracts = tmp_path / module.OUTCOME_CONTRACT_DIRNAME
    contracts.mkdir(parents=True)
    payload = {
        "contract_id": "notify-verified",
        "function": "client_notification",
        "state": "verified",
        "verify_by": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "evidence_summary": "NotificationHistory readback confirmed recipient/send",
    }
    (contracts / "notify-verified.json").write_text(json.dumps(payload), encoding="utf-8")

    failures, evidence = module.operational_outcome_contract_failures(tmp_path)

    assert failures == []
    assert evidence[0]["state"] == "verified"


def test_failed_jason_units_are_detected(monkeypatch):
    def fake_run(args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "jason-provider-health-canary.service loaded failed failed x\n"
                "unrelated.service loaded failed failed x\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(module, "run", fake_run)
    assert module.failed_jason_user_units() == [
        "jason-provider-health-canary.service"
    ]


def test_stale_client_notification_verification_is_detected(tmp_path):
    db = tmp_path / "work.sqlite3"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE autonomy_operational_work ("
        "ticket_id INTEGER,ticket_number TEXT,playbook_id TEXT,phase TEXT,"
        "updated_at TEXT,last_reason TEXT)"
    )
    conn.execute(
        "INSERT INTO autonomy_operational_work VALUES (?,?,?,?,?,?)",
        (
            123,
            "T20260930.0001",
            "vulscan_missing_patch",
            "vulscan_client_notification_verify_complete",
            (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
            "notification_baseline_id=42",
        ),
    )
    conn.commit()
    conn.close()

    failures, evidence = module.stale_operational_work_failures(db)

    assert failures == [
        "workflow_outcome_stale:vulscan_missing_patch:"
        "vulscan_client_notification_verify_complete:ticket=123"
    ]
    assert evidence[0]["ticket_number"] == "T20260930.0001"


def test_recent_client_notification_verification_is_not_stale(tmp_path):
    db = tmp_path / "work.sqlite3"
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE autonomy_operational_work ("
        "ticket_id INTEGER,ticket_number TEXT,playbook_id TEXT,phase TEXT,"
        "updated_at TEXT,last_reason TEXT)"
    )
    conn.execute(
        "INSERT INTO autonomy_operational_work VALUES (?,?,?,?,?,?)",
        (
            124,
            "T20260930.0002",
            "vulscan_missing_patch",
            "vulscan_client_notification_verify_monitoring",
            datetime.now(timezone.utc).isoformat(),
            "notification_baseline_id=43",
        ),
    )
    conn.commit()
    conn.close()

    failures, evidence = module.stale_operational_work_failures(db)

    assert failures == []
    assert evidence[0]["phase"] == "vulscan_client_notification_verify_monitoring"


def _create_admission_db(path: Path, *, eligible: int, active_slots: int, selected: int) -> None:
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE autonomy_ticket_scan_cycle ("
        "cycle_id TEXT,scanned_at TEXT,eligible INTEGER,active_slots INTEGER,selected INTEGER)"
    )
    conn.execute(
        "INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?,?)",
        (
            "cycle-1",
            datetime.now(timezone.utc).isoformat(),
            eligible,
            active_slots,
            selected,
        ),
    )
    conn.commit()
    conn.close()


def test_admission_stall_with_eligible_work_is_detected(tmp_path):
    db = tmp_path / "work.sqlite3"
    _create_admission_db(db, eligible=4, active_slots=2, selected=0)

    failures, evidence = module.autonomy_admission_failures(db)

    assert failures == ["autonomy_admission_stalled:eligible_work_not_selected"]
    assert evidence["eligible"] == 4
    assert evidence["active_slots"] == 2
    assert evidence["selected"] == 0


def test_no_admission_stall_when_no_eligible_work(tmp_path):
    db = tmp_path / "work.sqlite3"
    _create_admission_db(db, eligible=0, active_slots=2, selected=0)

    failures, evidence = module.autonomy_admission_failures(db)

    assert failures == []
    assert evidence["eligible"] == 0


def test_no_admission_stall_when_work_selected(tmp_path):
    db = tmp_path / "work.sqlite3"
    _create_admission_db(db, eligible=3, active_slots=2, selected=1)

    failures, evidence = module.autonomy_admission_failures(db)

    assert failures == []
    assert evidence["selected"] == 1


def _create_behavior_db(path: Path, rows: list[tuple]) -> None:
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE autonomy_ticket_scan_cycle ("
        "cycle_id TEXT,scanned_at TEXT,evaluated INTEGER,eligible INTEGER,"
        "unsupported INTEGER,governance_blocked INTEGER,assigned_elsewhere INTEGER,"
        "active_slots INTEGER,selected INTEGER,waiting_device INTEGER,human_review INTEGER)"
    )
    conn.executemany(
        "INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_generic_invariant_selected_cannot_exceed_eligible(tmp_path):
    db = tmp_path / "behavior.sqlite3"
    now_iso = datetime.now(timezone.utc).isoformat()
    _create_behavior_db(
        db,
        [("c1", now_iso, 4, 1, 0, 0, 0, 2, 2, 0, 0)],
    )

    failures, evidence = module.autonomy_behavior_anomalies(db)

    assert any("selected_gt_eligible" in item for item in failures)
    assert evidence["cycles"][0]["cycle_id"] == "c1"


def test_generic_invariant_selected_cannot_exceed_active_slots(tmp_path):
    db = tmp_path / "behavior.sqlite3"
    now_iso = datetime.now(timezone.utc).isoformat()
    _create_behavior_db(
        db,
        [("c2", now_iso, 4, 4, 0, 0, 0, 1, 2, 0, 0)],
    )

    failures, evidence = module.autonomy_behavior_anomalies(db)

    assert any("selected_gt_active_slots" in item for item in failures)
    assert evidence["cycles"][0]["cycle_id"] == "c2"


def test_behavior_baseline_detects_unexpected_selection_efficiency_collapse(tmp_path):
    db = tmp_path / "behavior.sqlite3"
    rows = []
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    for i in range(9):
        rows.append(
            (
                f"b{i}",
                (base + timedelta(minutes=i)).isoformat(),
                10, 10, 0, 0, 0, 2, 2, 0, 0,
            )
        )
    for i in range(3):
        rows.append(
            (
                f"r{i}",
                (base + timedelta(minutes=20 + i)).isoformat(),
                10, 10, 0, 0, 0, 2, 0, 0, 0,
            )
        )
    _create_behavior_db(db, rows)

    failures, evidence = module.autonomy_behavior_anomalies(db)

    assert "autonomy_behavior_anomaly:selection_efficiency_collapse" in failures
    assert evidence["selection_efficiency_baseline_median"] > 0
    assert evidence["selection_efficiency_recent_median"] == 0


def test_behavior_baseline_does_not_flag_consistent_low_activity(tmp_path):
    db = tmp_path / "behavior.sqlite3"
    rows = []
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    for i in range(12):
        rows.append(
            (
                f"c{i}",
                (base + timedelta(minutes=i)).isoformat(),
                10, 10, 0, 0, 0, 2, 0, 0, 0,
            )
        )
    _create_behavior_db(db, rows)

    failures, evidence = module.autonomy_behavior_anomalies(db)

    assert "autonomy_behavior_anomaly:selection_efficiency_collapse" not in failures


def _write_release_manager_fixture(root: Path, revision: str, *, legacy: bool = False) -> Path:
    release = root / revision
    (release / "tools").mkdir(parents=True)
    (release / "config").mkdir(parents=True)
    unit = release / "infrastructure/openclaw-operations/systemd/user"
    unit.mkdir(parents=True)
    (release / "tools/release_manager_host_runner.py").write_text("runner-v1\n", encoding="utf-8")
    timer = (
        "[Timer]\nOnCalendar=Mon..Fri *-*-* 17..23:00/5:00 America/New_York\n"
        if legacy
        else "[Timer]\nOnCalendar=*-*-* *:00/5:00 America/New_York\n"
    )
    (unit / "jason-release-manager.timer").write_text(timer, encoding="utf-8")
    policy_schedule = (
        {"automatic_promotion_enabled": True, "daily_window_local": "02:30"}
        if legacy
        else {"automatic_promotion_enabled": True, "mode": "continuous_24x7"}
    )
    coordinator_window = (
        {"enabled": True, "local_time": "02:30"}
        if legacy
        else {"enabled": True, "mode": "continuous_24x7"}
    )
    (release / "config/release-manager-policy.json").write_text(
        json.dumps({"schedule": policy_schedule}), encoding="utf-8"
    )
    (release / "config/development-release-coordinator.json").write_text(
        json.dumps({"production": {"automatic_window": coordinator_window}}),
        encoding="utf-8",
    )
    return release


def test_production_convergence_accepts_exact_live_release(tmp_path, monkeypatch):
    revision = "a" * 40
    releases = tmp_path / "releases"
    release = _write_release_manager_fixture(releases, revision)
    installed = tmp_path / "installed"
    installed.mkdir()
    source_link = installed / "release-manager-source"
    source_link.symlink_to(release, target_is_directory=True)
    runner = installed / "release_manager_host_runner.py"
    timer = installed / "jason-release-manager.timer"
    runner.write_bytes((release / "tools/release_manager_host_runner.py").read_bytes())
    timer.write_bytes(
        (release / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.timer").read_bytes()
    )

    monkeypatch.setattr(module, "_container_source_revision", lambda name: revision)
    monkeypatch.setattr(
        module,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="active\n", stderr=""),
    )

    failures, evidence = module.production_convergence_failures(
        release_manager_source_link=source_link,
        installed_runner=runner,
        installed_timer=timer,
        releases_root=releases,
    )

    assert failures == []
    assert evidence["desired_revision"] == revision
    assert evidence["release_manager_timer_active"] is True


def test_production_convergence_detects_stale_installed_release(tmp_path, monkeypatch):
    revision = "a" * 40
    old_revision = "b" * 40
    releases = tmp_path / "releases"
    release = _write_release_manager_fixture(releases, revision)
    old_release = _write_release_manager_fixture(releases, old_revision)
    installed = tmp_path / "installed"
    installed.mkdir()
    source_link = installed / "release-manager-source"
    source_link.symlink_to(old_release, target_is_directory=True)
    runner = installed / "release_manager_host_runner.py"
    timer = installed / "jason-release-manager.timer"
    runner.write_bytes((old_release / "tools/release_manager_host_runner.py").read_bytes())
    timer.write_bytes(
        (old_release / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.timer").read_bytes()
    )

    monkeypatch.setattr(module, "_container_source_revision", lambda name: revision)
    monkeypatch.setattr(
        module,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="active\n", stderr=""),
    )

    failures, _ = module.production_convergence_failures(
        release_manager_source_link=source_link,
        installed_runner=runner,
        installed_timer=timer,
        releases_root=releases,
    )

    assert "production_convergence_release_manager_source_drift" in failures


def test_production_convergence_detects_legacy_window_contradiction(tmp_path, monkeypatch):
    revision = "a" * 40
    releases = tmp_path / "releases"
    release = _write_release_manager_fixture(releases, revision, legacy=True)
    installed = tmp_path / "installed"
    installed.mkdir()
    source_link = installed / "release-manager-source"
    source_link.symlink_to(release, target_is_directory=True)
    runner = installed / "release_manager_host_runner.py"
    timer = installed / "jason-release-manager.timer"
    runner.write_bytes((release / "tools/release_manager_host_runner.py").read_bytes())
    timer.write_bytes(
        (release / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.timer").read_bytes()
    )

    monkeypatch.setattr(module, "_container_source_revision", lambda name: revision)
    monkeypatch.setattr(
        module,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="active\n", stderr=""),
    )

    failures, _ = module.production_convergence_failures(
        release_manager_source_link=source_link,
        installed_runner=runner,
        installed_timer=timer,
        releases_root=releases,
    )

    assert "production_convergence_intent_contradiction:release_manager_timer_not_24x7" in failures
    assert "production_convergence_intent_contradiction:release_policy_not_24x7" in failures
    assert "production_convergence_intent_contradiction:legacy_daily_window_present" in failures
    assert "production_convergence_intent_contradiction:coordinator_not_24x7" in failures
    assert "production_convergence_intent_contradiction:legacy_coordinator_time_present" in failures


def test_provider_canary_monitoring_rejects_stale_report(tmp_path, monkeypatch):
    report = tmp_path / "provider-health-canaries.json"
    report.write_text(
        json.dumps({"generated_at_epoch": 1.0, "results": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=1, stdout="inactive\n", stderr=""),
    )

    failures, evidence = module.provider_canary_monitoring_failures(
        report, max_age_seconds=60
    )

    assert "provider_canary_report_stale" in failures
    assert "provider_canary_timer_inactive" in failures
    assert evidence["fresh"] is False


def test_provider_canary_monitoring_accepts_fresh_report(tmp_path, monkeypatch):
    report = tmp_path / "provider-health-canaries.json"
    report.write_text(
        json.dumps(
            {
                "generated_at_epoch": datetime.now(timezone.utc).timestamp(),
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "run",
        lambda args, **kwargs: SimpleNamespace(returncode=0, stdout="active\n", stderr=""),
    )

    failures, evidence = module.provider_canary_monitoring_failures(
        report, max_age_seconds=60
    )

    assert failures == []
    assert evidence["fresh"] is True
    assert evidence["timer_active"] is True


def test_health_metrics_uses_headroom_for_slow_local_exporter(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b"jason_production_component_health{component=\"runtime\"} 1\n"

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    metrics, error = module.health_metrics()
    assert error is None
    assert calls == [(module.HEALTH_URL, 10)]
    assert metrics


def test_correlated_incident_persists_verification_and_recurrence_metadata(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    incident = {
        "fingerprint": "1234567890abcdef12345678",
        "family": "production_convergence",
        "title": "Production convergence incomplete",
        "root_invariant": "all production surfaces agree",
        "symptoms": ["production_convergence_scheduled_artifact_drift:self_heal_watchdog"],
        "priority": "P0",
        "occurrence_count": 2,
        "recurring": True,
        "architectural_correction_required": True,
        "repair": {
            "level": 2,
            "name": "bounded_autonomous_repair",
            "requires_owner_action": False,
        },
        "verification_contract": {
            "required_checks": ["rerun detector"],
            "closure_requires_detector_recheck": True,
        },
    }
    path = module.queue_resolution_incident(tmp_path, incident, {"sample": True})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["priority"] == "P0"
    assert payload["occurrence_count"] == 2
    assert payload["architectural_correction_required"] is True
    assert payload["requires_owner_action"] is False
    assert payload["verification_contract"]["closure_requires_detector_recheck"] is True
    assert calls[-1] == ["systemctl", "--user", "start", "--no-block", "jason-support-repair-worker.service"]


def test_level2_repair_exhaustion_does_not_escalate_to_owner(tmp_path, monkeypatch):
    import sys

    failure = "production_convergence_scheduled_artifact_drift:self_heal_watchdog"
    monkeypatch.setattr(module, "detect", lambda root: ([failure], {"sample": True}))
    monkeypatch.setattr(module, "bounded_recovery", lambda failures: [])
    monkeypatch.setattr(
        module,
        "queue_resolution_incident",
        lambda root, incident, evidence: root / "incidents" / f"{incident['fingerprint']}.json",
    )
    monkeypatch.setattr(
        module,
        "write_incident_escalation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not escalate Level 2")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["watchdog", "--root", str(tmp_path), "--max-attempts", "1"],
    )

    assert module.main() == 0
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "repair_required"
    assert state["owner_escalations"] == []
    assert state["incidents"][0]["repair"]["level"] == 2


def test_real_authority_boundary_can_escalate_after_bounded_attempts(tmp_path, monkeypatch):
    import sys

    failure = "provider_authority_required:microsoft_graph:admin_consent_required"
    monkeypatch.setattr(module, "detect", lambda root: ([failure], {"sample": True}))
    monkeypatch.setattr(module, "bounded_recovery", lambda failures: [])
    monkeypatch.setattr(
        module,
        "queue_resolution_incident",
        lambda root, incident, evidence: root / "incidents" / f"{incident['fingerprint']}.json",
    )
    monkeypatch.setattr(
        module,
        "write_incident_escalation",
        lambda root, **kwargs: root / "escalations" / "real-boundary.json",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["watchdog", "--root", str(tmp_path), "--max-attempts", "1"],
    )

    assert module.main() == 0
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "owner_action_required"
    assert len(state["owner_escalations"]) == 1
    assert state["incidents"][0]["repair"]["level"] == 4


def test_production_convergence_detects_scheduled_worker_drift(tmp_path, monkeypatch):
    revision = "c" * 40
    releases = tmp_path / "releases"
    release = _write_release_manager_fixture(releases, revision)
    desired_watchdog = release / "tools" / "jason_self_heal_watchdog.py"
    desired_watchdog.write_text("current-watchdog\n", encoding="utf-8")

    installed = tmp_path / "installed"
    installed.mkdir()
    source_link = installed / "release-manager-source"
    source_link.symlink_to(release, target_is_directory=True)
    current_link = installed / "current"
    current_link.symlink_to(release, target_is_directory=True)
    engineering = installed / "engineering-source"
    engineering.mkdir()
    runner = installed / "release_manager_host_runner.py"
    timer = installed / "jason-release-manager.timer"
    runner.write_bytes((release / "tools/release_manager_host_runner.py").read_bytes())
    timer.write_bytes(
        (release / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.timer").read_bytes()
    )
    stale_watchdog = installed / "jason_self_heal_watchdog.py"
    stale_watchdog.write_text("old-watchdog\n", encoding="utf-8")

    monkeypatch.setattr(module, "_container_source_revision", lambda name: revision)
    monkeypatch.setattr(module, "CURRENT_RELEASE_LINK", current_link)
    monkeypatch.setattr(module, "ENGINEERING_SOURCE_LINK", engineering)
    monkeypatch.setattr(
        module,
        "SCHEDULED_ARTIFACTS",
        (("self_heal_watchdog", "tools/jason_self_heal_watchdog.py", stale_watchdog),),
    )
    monkeypatch.setattr(module, "REQUIRED_USER_TIMERS", ("jason-release-manager.timer",))

    def fake_run(args, **kwargs):
        if args and args[0] == "git":
            return SimpleNamespace(returncode=0, stdout=revision + "\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="active\n", stderr="")

    monkeypatch.setattr(module, "run", fake_run)

    failures, evidence = module.production_convergence_failures(
        release_manager_source_link=source_link,
        installed_runner=runner,
        installed_timer=timer,
        releases_root=releases,
        verify_scheduled_surfaces=True,
    )

    assert "production_convergence_scheduled_artifact_drift:self_heal_watchdog" in failures
    assert evidence["engineering_source_revision"] == revision
    assert evidence["current_release"] == str(release.resolve())
