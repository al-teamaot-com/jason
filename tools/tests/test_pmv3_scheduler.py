import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

engine_spec = importlib.util.spec_from_file_location("pmv3_work_engine", ROOT / "tools/pmv3_work_engine.py")
engine = importlib.util.module_from_spec(engine_spec)
sys.modules[engine_spec.name] = engine
engine_spec.loader.exec_module(engine)

runner_spec = importlib.util.spec_from_file_location("pmv3_scheduler", ROOT / "tools/pmv3_scheduler.py")
runner = importlib.util.module_from_spec(runner_spec)
sys.modules[runner_spec.name] = runner
runner_spec.loader.exec_module(runner)


def write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_persists_state_across_cycles_and_does_not_duplicate(tmp_path):
    state = tmp_path / "state.json"
    work = tmp_path / "work.json"
    facts = tmp_path / "facts.json"
    approvals = tmp_path / "approvals.json"
    outcomes = tmp_path / "outcomes.json"
    status = tmp_path / "status.json"

    write(work, {"items": [{"id": "A", "action": "build"}]})
    write(facts, {})
    write(approvals, {"approvals": []})
    write(outcomes, {"A": [{"status": "complete", "receipt": "r-a"}]})

    first = runner.run_once(
        state_path=state, work_path=work, facts_path=facts,
        approvals_path=approvals, outcomes_path=outcomes,
        status_path=status, capacity=1,
    )
    assert first["progress_percent"] == 100
    persisted = engine.load_state(state)
    assert persisted["items"]["A"]["phase"] == "complete"
    assert len(persisted["receipts"]) == 1

    second = runner.run_once(
        state_path=state, work_path=work, facts_path=facts,
        approvals_path=approvals, outcomes_path=outcomes,
        status_path=status, capacity=1,
    )
    persisted = engine.load_state(state)
    assert second["admitted_this_cycle"] == 0
    assert persisted["items"]["A"]["attempts"] == 1
    assert len(persisted["receipts"]) == 1


def test_waiting_dependency_wakes_on_later_cycle(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{"id": "B", "action": "merge", "dependency": "checks_passed"}]})
    write(paths["facts"], {"checks_passed": False})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {"B": [{"status": "complete", "receipt": "r-b"}]})

    runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert engine.load_state(paths["state"])["items"]["B"]["phase"] == "waiting"

    write(paths["facts"], {"checks_passed": True})
    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 100


def test_teams_approval_required_and_persisted(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{
        "id": "C", "action": "release",
        "approval_required": True, "approval_request_id": "REQ-C"
    }]})
    write(paths["facts"], {})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {"C": [{"status": "complete", "receipt": "r-c"}]})

    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 0
    assert engine.load_state(paths["state"])["items"]["C"]["attempts"] == 0

    write(paths["approvals"], {"approvals": [{
        "item_id": "C", "request_id": "REQ-C", "decision": "approve",
        "actor_id": "person-al", "tenant_id": "tenant-aot",
        "receipt_id": "teams-receipt-c", "verified": True, "channel": "teams"
    }]})
    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 100
    persisted = engine.load_state(paths["state"])
    assert persisted["items"]["C"]["approval"]["channel"] == "teams"


def test_non_teams_approval_input_fails_closed(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{
        "id": "D", "action": "release",
        "approval_required": True, "approval_request_id": "REQ-D"
    }]})
    write(paths["facts"], {})
    write(paths["approvals"], {"approvals": [{
        "item_id": "D", "request_id": "REQ-D", "decision": "approve",
        "actor_id": "person-al", "tenant_id": "tenant-aot",
        "receipt_id": "shell-d", "verified": True, "channel": "ssh"
    }]})
    write(paths["outcomes"], {"D": [{"status": "complete", "receipt": "r-d"}]})

    try:
        runner.run_once(
            state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
            approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
            status_path=paths["status"], capacity=1,
        )
    except ValueError as exc:
        assert "Teams" in str(exc)
    else:
        raise AssertionError("non-Teams approval must fail closed")


def test_verified_entra_owner_ingress_does_not_need_teams(tmp_path):
    paths = {
        name: tmp_path / (name + ".json")
        for name in ("state", "work", "facts", "approvals", "outcomes", "status")
    }
    write(paths["work"], {"items": [{
        "id": "OWNER-OAUTH", "action": "non-disruptive-verification",
        "approval_required": True, "approval_request_id": "REQ-OAUTH",
    }]})
    write(paths["facts"], {})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {
        "OWNER-OAUTH": [{"status": "complete", "receipt": "owner-ok"}],
    })
    first = runner.run_once(
        state_path=paths["state"], work_path=paths["work"],
        facts_path=paths["facts"], approvals_path=paths["approvals"],
        outcomes_path=paths["outcomes"], status_path=paths["status"],
        capacity=1,
    )
    assert first["progress_percent"] == 0
    item = engine.load_state(paths["state"])["items"]["OWNER-OAUTH"]
    raw = {"item_id": "OWNER-OAUTH", "opaque_evidence": {"signed_ref": "mocked"}}
    trusted = lambda _: {
        "issuer": "jason_entra_owner_authority",
        "authentication": "entra_oauth_bearer",
        "identity_status": "active",
        "owner_identity_id": "person-al",
        "microsoft_tenant_id": engine.OWNER_TENANT_ID,
        "microsoft_object_id": engine.OWNER_ENTRA_OBJECT_ID,
        "request_id": item["approval_request_id"],
        "action_scope_sha256": engine.owner_approval_scope(item),
        "decision": "approve",
        "receipt_id": "mocked-independent-owner-receipt",
        "proof_sha256": "a" * 64,
    }
    second = runner.run_once(
        state_path=paths["state"], work_path=paths["work"],
        facts_path=paths["facts"], approvals_path=paths["approvals"],
        outcomes_path=paths["outcomes"], status_path=paths["status"],
        capacity=1,
        authenticated_owner_decisions=[raw],
        trusted_owner_verifier=trusted,
    )
    assert second["authenticated_owner_approvals_applied"] == 1
    assert second["teams_approvals_applied"] == 0
    assert second["progress_percent"] == 100
    actual = engine.load_state(paths["state"])["items"]["OWNER-OAUTH"]
    assert actual["phase"] == "complete"
    assert actual["approval"]["channel"] == "authenticated_owner"


def test_governed_owner_ingress_fails_closed_without_trusted_verifier(tmp_path):
    state = engine.empty_state()
    engine.admit(state, engine.make_item(
        "NO-VERIFIER", "release", approval_required=True,
        approval_request_id="NO-VERIFIER-REQ",
    ))
    try:
        runner.ingest_authenticated_owner_decisions(
            state,
            [{"item_id": "NO-VERIFIER", "opaque_evidence": {"verified": True}}],
            verified_decision=None,
        )
    except runner.SchedulerInputError as exc:
        assert "verifier" in str(exc)
    else:
        raise AssertionError("raw approval without trusted verifier accepted")
    assert not engine.approval_satisfied(state["items"]["NO-VERIFIER"])


def test_governed_owner_ingress_rejects_wrong_tenant_from_adapter(tmp_path):
    state = engine.empty_state()
    engine.admit(state, engine.make_item(
        "WRONG-TENANT", "release", approval_required=True,
        approval_request_id="REQ-WRONG-TENANT",
    ))
    item = state["items"]["WRONG-TENANT"]
    try:
        runner.ingest_authenticated_owner_decisions(
            state,
            [{"item_id": "WRONG-TENANT", "opaque_evidence": {"signed_ref": "mock"}}],
            verified_decision=lambda _: {
                "issuer": "jason_entra_owner_authority",
                "authentication": "entra_oauth_bearer",
                "identity_status": "active",
                "owner_identity_id": "person-al",
                "microsoft_tenant_id": "other-tenant",
                "microsoft_object_id": engine.OWNER_ENTRA_OBJECT_ID,
                "request_id": item["approval_request_id"],
                "action_scope_sha256": engine.owner_approval_scope(item),
                "decision": "approve",
                "receipt_id": "untrusted",
                "proof_sha256": "a" * 64,
            },
        )
    except ValueError as exc:
        assert "not exact" in str(exc)
    else:
        raise AssertionError("cross-tenant approval accepted")
    assert not engine.approval_satisfied(item)


def test_cli_file_cannot_enable_authenticated_owner_path(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in (
        "state", "work", "facts", "approvals", "outcomes", "status")}
    write(paths["work"], {"items": [{
        "id": "RAW-FILE", "action": "release",
        "approval_required": True, "approval_request_id": "RAW-REQ",
    }]})
    write(paths["facts"], {})
    write(paths["outcomes"], {"RAW-FILE": [{"status": "complete", "receipt": "bad"}]})
    write(paths["approvals"], {"approvals": [{
        "item_id": "RAW-FILE", "request_id": "RAW-REQ",
        "decision": "approve", "actor_id": "person-al",
        "tenant_id": engine.OWNER_TENANT_ID, "receipt_id": "forge",
        "verified": True, "channel": "authenticated_owner",
    }]})
    try:
        runner.run_once(
            state_path=paths["state"], work_path=paths["work"],
            facts_path=paths["facts"], approvals_path=paths["approvals"],
            outcomes_path=paths["outcomes"], status_path=paths["status"], capacity=1,
        )
    except ValueError as exc:
        assert "Teams" in str(exc)
    else:
        raise AssertionError("forged approval through local JSON was accepted")
