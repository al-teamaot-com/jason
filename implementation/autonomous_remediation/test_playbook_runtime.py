from pathlib import Path
import pytest
from playbook_runtime import FilePlaybookRunStore, PlaybookRunRecord, RunState


def record() -> PlaybookRunRecord:
    return PlaybookRunRecord(run_id="hosts-test-1", playbook_id="hosts_file_drift", playbook_version="0.1.0", ticket_id="T-TEST", company_id="827", device_id="device-test", trigger_class="monitor_alert")


def test_run_persists_and_resumes_without_losing_state(tmp_path: Path):
    store=FilePlaybookRunStore(tmp_path); run=record(); store.create(run)
    run.transition(RunState.IDENTIFYING); run.record_step("bind_context","pass",evidence_refs=("ev-1",)); run.transition(RunState.DIAGNOSING); store.save(run)
    restored=store.load(run.run_id)
    assert restored.state == RunState.DIAGNOSING
    assert restored.completed_steps[0].name == "bind_context"
    assert restored.evidence_refs == ["ev-1"]


def test_invalid_transition_fails_closed():
    run=record()
    with pytest.raises(ValueError, match="invalid playbook transition"):
        run.transition(RunState.COMPLETE)


def test_exact_approval_binding_and_resume():
    run=record(); run.transition(RunState.IDENTIFYING); run.transition(RunState.DIAGNOSING); run.transition(RunState.DECIDING); run.require_approval("approval-1")
    with pytest.raises(ValueError, match="does not match"):
        run.approve("approval-other")
    run.approve("approval-1"); run.transition(RunState.REMEDIATING)
    assert run.state == RunState.REMEDIATING and run.approval_status == "approved"


def test_recheck_and_terminal_behavior():
    run=record(); run.transition(RunState.IDENTIFYING); run.transition(RunState.DIAGNOSING); run.schedule_recheck("2026-09-19T14:00:00Z")
    assert run.state == RunState.RECHECK_PENDING
    run.transition(RunState.VERIFYING); run.transition(RunState.COMPLETE)
    assert run.terminal and run.outcome == "resolved"
    with pytest.raises(ValueError, match="terminal"):
        run.record_step("late","pass")


def test_store_rejects_duplicate_and_unsafe_run_id(tmp_path: Path):
    store=FilePlaybookRunStore(tmp_path); run=record(); store.create(run)
    with pytest.raises(ValueError, match="already exists"): store.create(run)
    bad=record(); bad.run_id="../bad"
    with pytest.raises(ValueError, match="invalid run id"): store.save(bad)
