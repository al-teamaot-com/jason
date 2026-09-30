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
