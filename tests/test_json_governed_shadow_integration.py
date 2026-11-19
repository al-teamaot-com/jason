"""Source-only end-to-end simulated governed read integration acceptance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from implementation.autonomous_remediation.playbook_document import validate_playbook_document
from implementation.autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, JsonShadowBoundaryError, SQLiteJsonShadowState)
from implementation.autonomous_remediation.json_shadow_facts import reduce_daily_drmm_alert

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/drmm_recent_alert_reconciliation.v1.json"
NOW = datetime(2026, 11, 19, 15, tzinfo=timezone.utc)
READS = frozenset({
    "management.alert.search", "endpoint.device.read",
    "endpoint.security.status.read", "endpoint.security.detection.search",
    "endpoint.alert.history.search", "service.ticket.search", "service.ticket.read",
})


class FakeGovernedObserve:
    def __init__(self, *, case="unsupported"):
        self.case = case
        self.bound_client_id = "company-1"
        self.calls = []
        self.mutations = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        assert capability in READS, "must never call an unapproved capability"
        if capability == "management.alert.search":
            assert arguments == {"status": "open"}
            stamp = NOW - (timedelta(hours=25) if self.case == "old" else timedelta(hours=1))
            alert_class = ("endpoint_security_threat_ctx"
                           if self.case != "unsupported" else "eventlog_ctx")
            records = [{
                "alertUid": "alert-1", "timestamp": int(stamp.timestamp() * 1000),
                "alertSourceInfo": {"deviceUid": "device-1"},
                "alertContext": {"@class": alert_class},
                "ticketNumber": "T-SYNTHETIC",
            }]
            if self.case == "ambiguous":
                records.append(dict(records[0]))
            return {"status": "succeeded", "evidence": {"data": {"alerts": records}}}
        if capability == "endpoint.device.read":
            assert arguments == {"resource_id": "device-1"}
            if self.case == "offline":
                online = False
            else:
                online = True
            if self.case == "identity_mismatch":
                uid = "wrong-tenant-device"
            else:
                uid = "device-1"
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": uid, "online": online}}}
        if capability == "endpoint.security.status.read":
            assert arguments == {"resource_id": "device-1"}
            return {"status": "succeeded", "evidence": {"data": {"resource_matches": [{
                "device_uid": "device-1", "agent_id": "agent-1",
                "datto_av": {"enabled": True, "connected": True, "engine_ready": True},
            }]}}}
        if capability == "endpoint.security.detection.search":
            assert arguments == {"agent_id": "agent-1", "archived": False, "limit": 50}
            detections = [{"id": "active-1"}] if self.case == "active" else []
            return {"status": "succeeded", "evidence": {"data": {"alerts": detections}}}
        raise AssertionError("unexpected capability read")


def setup(tmp_path, *, case="unsupported", read_capabilities=READS, version=None):
    doc = json.loads(CANDIDATE.read_text())
    if version:
        doc["playbook"]["version"] = version
    document = validate_playbook_document(doc)
    state = SQLiteJsonShadowState(tmp_path / "isolated-shadow.sqlite3")
    reads = FakeGovernedObserve(case=case)
    engine = GovernedJsonShadowIntegration(
        document=document, state=state, read_port=reads,
        read_capabilities=read_capabilities,
        normalize=lambda cap, res, facts: reduce_daily_drmm_alert(
            cap, res, facts, at=NOW),
        clock=lambda: NOW,
    )
    return engine, reads, state


def run(engine, **kwargs):
    return engine.run(
        run_id="synthetic-run-1", client_id="company-1", target_id="alert-1",
        trusted_seed={"client_id": "company-1", "target_id": "alert-1"}, **kwargs)


@pytest.mark.parametrize("case,expected,reads", [
    ("unsupported", "completed_readonly", 1),
    ("old", "completed_readonly", 1),
    ("offline", "completed_readonly", 2),
    ("active", "completed_readonly", 4),
    ("healthy", "completed_readonly", 4),
])
def test_exact_governed_reads_and_fail_closed_no_writes(tmp_path, case, expected, reads):
    runner, port, state = setup(tmp_path, case=case)
    result = run(runner)
    assert result.status == expected
    assert len(port.calls) == reads
    assert port.mutations == []
    assert result.fingerprint == runner.document.fingerprint
    assert result.history
    assert all(h.get("type") not in ("remediation", "document")
               for h in result.history)
    assert "exact_reconciliation_owner_promotion_verified" not in result.facts
    state.close()


def test_isolated_shadow_restart_is_idempotent_and_version_bound(tmp_path):
    runner, port, state = setup(tmp_path, case="active")
    partial = run(runner, max_steps=1)
    assert partial.status == "step_budget_exhausted"
    assert len(port.calls) == 1
    state.close()
    resumed, second_port, db = setup(tmp_path, case="active")
    result = run(resumed)
    assert result.status == "completed_readonly"
    assert len(second_port.calls) == 3
    before = len(second_port.calls)
    same = run(resumed)
    assert same == result
    assert len(second_port.calls) == before
    db.close()
    changed, _, db = setup(tmp_path, case="active", version="1.0.1-migration.1")
    with pytest.raises(JsonShadowBoundaryError, match="RUN_RESUME_IDENTITY_OR_VERSION_CHANGED"):
        run(changed)
    db.close()


@pytest.mark.parametrize("case", ["ambiguous", "identity_mismatch"])
def test_ambiguous_or_mismatched_source_never_advances(tmp_path, case):
    runner, port, state = setup(tmp_path, case=case)
    result = run(runner)
    assert result.status == "failed_closed"
    assert port.mutations == []
    assert all(item.get("result") != "NO_MUTATION_IN_SHADOW"
               for item in result.history)
    state.close()


def test_disallowed_read_capability_blocks_before_call(tmp_path):
    runner, port, state = setup(tmp_path, read_capabilities=frozenset())
    result = run(runner)
    assert result.status == "failed_closed"
    assert port.calls == []
    assert result.history[-1]["result"] == "READ_CAPABILITY_DENIED"
    state.close()


@pytest.mark.parametrize("seed", [
    {"client_id": "company-1", "target_id": "alert-1",
     "exact_reconciliation_owner_promotion_verified": True},
    {"client_id": "company-1", "target_id": "alert-1",
     "exact_agent_and_av_engine_healthy": True},
])
def test_seed_cannot_invent_trusted_authority_or_health(tmp_path, seed):
    runner, port, state = setup(tmp_path)
    with pytest.raises(JsonShadowBoundaryError, match="SEED_FACTS_NOT_TRUSTED"):
        runner.run(run_id="synthetic-run-1", client_id="company-1",
                   target_id="alert-1", trusted_seed=seed)
    assert port.calls == []
    state.close()


def test_cannot_resume_different_tenant_under_same_run_id(tmp_path):
    runner, port, state = setup(tmp_path)
    run(runner)
    port.bound_client_id = "different-company"
    with pytest.raises(JsonShadowBoundaryError, match="RUN_RESUME_IDENTITY_OR_VERSION_CHANGED"):
        runner.run(run_id="synthetic-run-1", client_id="different-company",
                   target_id="alert-1",
                   trusted_seed={"client_id": "different-company", "target_id": "alert-1"})
    state.close()


def test_normalizer_cannot_manufacture_approval_facts(tmp_path):
    runner, port, state = setup(tmp_path)
    runner.normalize = lambda *_: {"exact_reconciliation_owner_promotion_verified": True}
    result = run(runner)
    assert result.status == "failed_closed"
    assert len(port.calls) == 1
    state.close()


def test_governed_read_failure_stays_fail_closed_after_restart(tmp_path):
    runner, port, state = setup(tmp_path)
    port.execute = lambda *_: {"status": "denied"}
    result = run(runner)
    assert result.status == "failed_closed"
    state.close()
    resumed, new_port, db = setup(tmp_path)
    assert run(resumed).status == "failed_closed"
    assert new_port.calls == []
    db.close()


def test_bare_terminal_document_cannot_claim_shadow_success(tmp_path):
    from implementation.autonomous_remediation.playbook_document import validate_playbook_document
    doc = validate_playbook_document({
        "schema_version": 1,
        "playbook": {"id": "no_evidence_pilot", "name": "No Evidence",
                     "version": "0.0.1", "lifecycle": "pilot",
                     "target_type": "provider_object"},
        "state_model": {"entry_step": "complete_without_read"},
        "steps": [{"id": "complete_without_read", "type": "complete"}],
        "verification": {"authoritative_source": "none",
                         "success_condition": "must not claim completion"},
        "completion": {"terminal_disposition": "none"},
        "scope": {"direct_provider_access": False},
        "autonomy": {"activation": "shadow", "allowed_capabilities": []},
    })
    state = SQLiteJsonShadowState(tmp_path / "bare.sqlite3")
    runner = GovernedJsonShadowIntegration(
        document=doc, state=state, read_port=FakeGovernedObserve(),
        read_capabilities=frozenset(), normalize=lambda *_: {}, clock=lambda: NOW,
    )
    result = runner.run(run_id="bare", client_id="company-1", target_id="alert-1",
                        trusted_seed={"client_id": "company-1", "target_id": "alert-1"})
    assert result.status == "failed_closed"
    assert result.history[-1]["result"] == "NO_AUTHORITATIVE_READ_EVIDENCE"
    state.close()


def test_wait_durable_clock_recheck_and_no_early_replay(tmp_path):
    payload = json.loads(CANDIDATE.read_text())
    # Keep one normal governed read; make its subsequent bounded recheck a
    # declarative wait, with a new immutable candidate version.
    payload["playbook"]["id"] = "drmm_wait_shadow_pilot"
    payload["playbook"]["version"] = "0.0.1-migration.1"
    payload["steps"] = [
        {"id": "read_open_alerts", "type": "diagnostic",
         "capability": "management.alert.search", "arguments": {"status": "open"},
         "next": "wait_next"},
        {"id": "wait_next", "type": "wait", "seconds": 60, "resume": "complete"},
        {"id": "complete", "type": "complete"},
    ]
    payload["state_model"]["entry_step"] = "read_open_alerts"
    document = validate_playbook_document(payload)
    time = [NOW]
    state = SQLiteJsonShadowState(tmp_path / "wait.sqlite3")
    port = FakeGovernedObserve()
    runner = GovernedJsonShadowIntegration(
        document=document, state=state, read_port=port,
        read_capabilities=READS,
        normalize=lambda cap, response, facts: reduce_daily_drmm_alert(
            cap, response, facts, at=time[0]),
        clock=lambda: time[0],
    )
    kwargs = dict(run_id="wait-1", client_id="company-1", target_id="alert-1",
                  trusted_seed={"client_id": "company-1", "target_id": "alert-1"})
    initial = runner.run(**kwargs)
    assert initial.status == "waiting"
    assert len(port.calls) == 1
    time[0] += timedelta(seconds=59)
    assert runner.run(**kwargs).status == "waiting"
    assert len(port.calls) == 1
    state.close()

    resumed_store = SQLiteJsonShadowState(tmp_path / "wait.sqlite3")
    resumed = GovernedJsonShadowIntegration(
        document=document, state=resumed_store, read_port=port,
        read_capabilities=READS, normalize=runner.normalize, clock=lambda: time[0],
    )
    time[0] += timedelta(seconds=1)
    result = resumed.run(**kwargs)
    assert result.status == "completed_readonly"
    assert len(port.calls) == 1
    assert result.history[-1]["step_id"] == "complete"
    resumed_store.close()


def test_mutation_is_never_executed_even_with_forged_port(tmp_path):
    payload = json.loads(CANDIDATE.read_text())
    doc = validate_playbook_document(payload)
    state = SQLiteJsonShadowState(tmp_path / "mutation.sqlite3")
    port = FakeGovernedObserve(case="healthy")
    # A test-only normalizer returns positive health and even tries to
    # provide approval as a trusted read fact; the bridge must deny it.
    runner = GovernedJsonShadowIntegration(
        document=doc, state=state, read_port=port, read_capabilities=READS,
        normalize=lambda cap, result, facts: {
            **reduce_daily_drmm_alert(cap, result, facts, at=NOW),
            "exact_reconciliation_owner_promotion_verified": True,
        },
        clock=lambda: NOW,
    )
    result = run(runner)
    assert result.status == "failed_closed"
    assert result.history[-1]["result"] == "JsonShadowBoundaryError"
    assert port.mutations == []
    state.close()


def test_exact_synthetic_owner_promotion_produces_plan_only_no_mutation(tmp_path):
    from implementation.autonomous_remediation.playbook_autonomy_approval import (
        PlaybookAutonomyApproval, SQLitePlaybookAutonomyApprovalStore,
    )
    doc = validate_playbook_document(json.loads(CANDIDATE.read_text()))
    approval = SQLitePlaybookAutonomyApprovalStore(tmp_path / "approval-test.sqlite3")
    capabilities = tuple(sorted({
        step["capability"] for step in doc.payload["steps"]
        if step["type"] in {"remediation", "document"}
    }))
    approval.put(PlaybookAutonomyApproval(
        approval_id="synthetic-only-never-production",
        playbook_id=doc.playbook_id,
        playbook_version=doc.version,
        policy_id=f"playbook-autonomy:{doc.playbook_id}",
        allowed_capabilities=capabilities,
        approved_by="fixture-only-test",
        approved_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
    ))
    runner, port, state = setup(tmp_path, case="healthy")
    runner.promotion_store = approval
    runner.promotion_fact_name = "exact_reconciliation_owner_promotion_verified"
    runner.mutation_capabilities = capabilities
    result = run(runner)
    assert result.status == "blocked_mutation"
    assert result.step_id == "resolve_alert"
    assert result.history[-1]["capability"] == "endpoint.alert.resolve"
    assert result.history[-1]["result"] == "NO_MUTATION_IN_SHADOW"
    assert "exact_reconciliation_owner_promotion_verified" not in result.facts
    assert port.mutations == []
    assert len(port.calls) == 4
    state.close()
    approval.close()


def test_wrong_version_synthetic_promotion_never_unlocks_mutation(tmp_path):
    from implementation.autonomous_remediation.playbook_autonomy_approval import (
        PlaybookAutonomyApproval, SQLitePlaybookAutonomyApprovalStore,
    )
    runner, port, state = setup(tmp_path, case="healthy")
    approval = SQLitePlaybookAutonomyApprovalStore(tmp_path / "approval-test.sqlite3")
    capabilities = tuple(sorted(runner.mutation_capabilities))
    approval.put(PlaybookAutonomyApproval(
        approval_id="synthetic-wrong-version",
        playbook_id=runner.document.playbook_id,
        playbook_version="1.0.0",  # legacy version, not migration version
        policy_id=f"playbook-autonomy:{runner.document.playbook_id}",
        allowed_capabilities=capabilities,
        approved_by="fixture-only-test", approved_at=NOW,
    ))
    runner.promotion_store = approval
    runner.promotion_fact_name = "exact_reconciliation_owner_promotion_verified"
    result = run(runner)
    assert result.status == "completed_readonly"
    assert result.step_id == "skip_no_mutation"
    assert port.mutations == []
    state.close()
    approval.close()


def test_unbound_or_cross_client_read_port_never_invoked(tmp_path):
    runner, port, state = setup(tmp_path)
    port.bound_client_id = "different-company"
    with pytest.raises(JsonShadowBoundaryError, match="CLIENT_SCOPE_UNVERIFIED"):
        run(runner)
    assert port.calls == []
    del port.bound_client_id
    with pytest.raises(JsonShadowBoundaryError, match="CLIENT_SCOPE_UNVERIFIED"):
        run(runner)
    assert port.calls == []
    state.close()
