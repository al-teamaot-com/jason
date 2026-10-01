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
    assert calls[-1][:4] == ["systemctl", "--user", "start", "jason-support-repair-worker.service"]


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
