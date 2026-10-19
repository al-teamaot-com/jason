import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("engineering_supervisor", TOOLS / "engineering_supervisor.py")
supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = supervisor
spec.loader.exec_module(supervisor)


def write(spool, name, value):
    spool.mkdir(exist_ok=True)
    (spool / name).write_text(json.dumps(value))


def test_supervisor_reports_internal_stall_and_tracks_forward_progress(tmp_path):
    write(tmp_path, "state.json", {"items": {
        "SUPPORT-OPS-054": {"phase": "blocked", "reason": "Missing exact source excerpt"},
        "SUPPORT-OPS-999": {"phase": "complete"},
    }})
    write(tmp_path, "development-state.json", {"items": {
        "DEV-1459": {"phase": "blocked", "reason": "development reasoning failed: HTTP transport failed"},
    }})
    write(tmp_path, "todo-intake-state.json", {
        "active_development_items": 0, "active_support_repairs": 0,
        "engineering_capacity": 3,
        "downstream_commitments": {
            "outstanding_count": 7,
            "items": [
                {"id": "TODO-OPS-002", "phase": "development_blocked",
                 "reason": "Datto API details and credentials unavailable"},
                {"id": "TODO-OPS-001", "phase": "waiting_operational_acceptance",
                 "reason": "Production acceptance required"},
            ],
        },
    })
    first = supervisor.build_snapshot(tmp_path)
    assert first["status"] == "degraded"
    assert first["reason"] == "internal_recovery_needed"
    assert first["category_counts"]["recoverable_source"] == 1
    assert first["category_counts"]["recoverable_transport"] == 1
    assert first["category_counts"]["external_dependency"] == 1
    assert first["category_counts"]["acceptance"] == 1
    assert first["unchanged_cycles"] == 0
    second = supervisor.build_snapshot(tmp_path, first)
    assert second["unchanged_cycles"] == 1
    supervisor.atomic_write(tmp_path / "engineering-supervisor-state.json", second)
    assert (tmp_path / "engineering-supervisor-state.json").stat().st_mode & 0o777 == 0o600
    write(tmp_path, "development-state.json", {"items": {
        "DEV-1459": {"phase": "diagnosing"},
    }})
    changed = supervisor.build_snapshot(tmp_path, second)
    assert changed["unchanged_cycles"] == 0


def test_supervisor_detects_real_model_turn_without_phase_change(tmp_path):
    write(tmp_path, "state.json", {"items": {
        "SUPPORT-OPS-054": {"phase": "implementing", "reasoning_request_id": "a" * 64},
        "SUPPORT-OPS-077": {"phase": "blocked", "reason": "old closed historical"},
    }, "support_state_mismatches": {"support_open_issue_not_open": ["SUPPORT-OPS-077"]}})
    write(tmp_path, "development-state.json", {"items": {}})
    write(tmp_path, "todo-intake-state.json", {
        "active_development_items": 1, "active_support_repairs": 0,
        "engineering_capacity": 2, "downstream_commitments": {"outstanding_count": 1},
    })
    first = supervisor.build_snapshot(tmp_path)
    assert first["status"] == "healthy"
    assert not any(i["id"] == "SUPPORT-OPS-077" for i in first["items"])
    second = supervisor.build_snapshot(tmp_path, first)
    assert second["unchanged_cycles"] == 1
    write(tmp_path, "state.json", {"items": {
        "SUPPORT-OPS-054": {"phase": "implementing", "reasoning_request_id": "b" * 64},
    }})
    third = supervisor.build_snapshot(tmp_path, second)
    assert third["unchanged_cycles"] == 0


def test_supervisor_fails_closed_on_bad_work_inventory(tmp_path):
    write(tmp_path, "state.json", {"items": []})
    write(tmp_path, "development-state.json", {"items": {}})
    write(tmp_path, "todo-intake-state.json", {"downstream_commitments": {}})
    with pytest.raises(ValueError, match="inventory"):
        supervisor.build_snapshot(tmp_path)


def test_supervisor_does_not_turn_genuine_authority_hold_into_recovery():
    phase = "development_blocked"
    assert supervisor.classify(phase, "Credential needed for client API", lane="approved_todo")[0] == "external_dependency"
    assert supervisor.classify(phase, "Do not begin until prerequisite fixed", lane="approved_todo")[0] == "dependency_hold"
    assert supervisor.classify(phase, "Owner approval required", lane="approved_todo")[0] == "human_authority"
    assert supervisor.classify("pr_ready", "", lane="development")[0] == "integration_review"


def test_evidence_budget_exhaustion_reports_actionable_verified_upgrade_not_generic_triage():
    from engineering_supervisor import classify
    category, action = classify(
        "blocked", "EvidenceToolError: source evidence turn budget exhausted",
        lane="support",
    )
    assert category == "recoverable_source"
    assert action == "native_worker_verify_source_upgrade_or_escalate"
