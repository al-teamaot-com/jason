from pathlib import Path
import pytest
from playbook_coordinator import PlaybookIdentity, PlaybookRunCoordinator
from playbook_runtime import FilePlaybookRunStore, RunState


def coordinator(tmp_path: Path):
    return PlaybookRunCoordinator(FilePlaybookRunStore(tmp_path))


def test_ensure_run_reuses_same_active_work_item(tmp_path: Path):
    c=coordinator(tmp_path); ident=PlaybookIdentity("hosts_file_drift","0.1.0")
    first=c.ensure_run(identity=ident,run_id="run-1",ticket_id="T1",company_id="827",device_id="D1")
    second=c.ensure_run(identity=ident,run_id="run-2",ticket_id="T1",company_id="827",device_id="D1")
    assert first.run_id == second.run_id == "run-1"


def test_version_mismatch_fails_closed(tmp_path: Path):
    c=coordinator(tmp_path)
    c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.1.0"),run_id="run-1",ticket_id="T1",company_id="827")
    with pytest.raises(ValueError,match="version mismatch"):
        c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.2.0"),run_id="run-2",ticket_id="T1",company_id="827")


def test_governed_action_result_persists_evidence_and_attempt(tmp_path: Path):
    c=coordinator(tmp_path); run=c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.1.0"),run_id="run-1",ticket_id="T1",company_id="827")
    c.transition(run,RunState.IDENTIFYING); c.transition(run,RunState.DIAGNOSING); c.transition(run,RunState.DECIDING); c.transition(run,RunState.REMEDIATING)
    c.record_governed_action_result(run,step="remove_unauthorized_hosts_entry",status="completed",correlation_id="corr-1",job_id="job-1")
    restored=c.store.load("run-1")
    assert restored.attempt_count == 1
    assert restored.evidence_refs == ["corr-1","job-1"]


def test_multiple_active_duplicates_fail_closed(tmp_path: Path):
    store=FilePlaybookRunStore(tmp_path)
    from playbook_runtime import PlaybookRunRecord
    store.create(PlaybookRunRecord(run_id="a",playbook_id="p",playbook_version="1",ticket_id="T",company_id="C"))
    store.create(PlaybookRunRecord(run_id="b",playbook_id="p",playbook_version="1",ticket_id="T",company_id="C"))
    c=PlaybookRunCoordinator(store)
    with pytest.raises(ValueError,match="multiple active"):
        c.ensure_run(identity=PlaybookIdentity("p","1"),run_id="c",ticket_id="T",company_id="C")


def test_governed_executor_records_real_orchestrator_result_shape(tmp_path: Path):
    from types import SimpleNamespace
    from playbook_coordinator import GovernedPlaybookExecutor
    c=coordinator(tmp_path); run=c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.1.0"),run_id="run-1",ticket_id="T1",company_id="827")
    c.transition(run,RunState.IDENTIFYING); c.transition(run,RunState.DIAGNOSING); c.transition(run,RunState.DECIDING); c.transition(run,RunState.REMEDIATING)
    class Orchestrator:
        def execute(self, request):
            assert request == "governed-request"
            return SimpleNamespace(status=SimpleNamespace(value="succeeded"), correlation_id="corr-governed-1", attempts=1, reason_codes=("capability_completed",))
    result=GovernedPlaybookExecutor(Orchestrator(),c).execute(run,step="governed_remediation",request="governed-request",success_state=RunState.VERIFYING)
    restored=c.store.load("run-1")
    assert result.correlation_id == "corr-governed-1"
    assert restored.state == RunState.VERIFYING
    assert restored.attempt_count == 1
    assert restored.evidence_refs == ["corr-governed-1"]


def test_governed_executor_blocks_without_retry_on_approval_required(tmp_path: Path):
    from types import SimpleNamespace
    from playbook_coordinator import GovernedPlaybookExecutor
    c=coordinator(tmp_path); run=c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.1.0"),run_id="run-1",ticket_id="T1",company_id="827")
    c.transition(run,RunState.IDENTIFYING); c.transition(run,RunState.DIAGNOSING); c.transition(run,RunState.DECIDING)
    class Orchestrator:
        calls=0
        def execute(self, request):
            self.calls+=1
            return SimpleNamespace(status=SimpleNamespace(value="approval_required"), correlation_id="corr-approval", attempts=0, reason_codes=("APPROVAL_REQUIRED",))
    o=Orchestrator(); GovernedPlaybookExecutor(o,c).execute(run,step="proposed_change",request="request")
    restored=c.store.load("run-1")
    assert o.calls == 1
    assert restored.state == RunState.BLOCKED
    assert restored.blocked_reason_class == "approval_required"
    assert restored.attempt_count == 0


def test_governed_executor_rejects_invalid_success_transition_before_dispatch(tmp_path: Path):
    from playbook_coordinator import GovernedPlaybookExecutor
    c=coordinator(tmp_path); run=c.ensure_run(identity=PlaybookIdentity("hosts_file_drift","0.1.0"),run_id="run-1",ticket_id="T1",company_id="827")
    class Orchestrator:
        calls=0
        def execute(self, request):
            self.calls += 1
            raise AssertionError("must not dispatch")
    o=Orchestrator()
    with pytest.raises(ValueError,match="invalid playbook success transition"):
        GovernedPlaybookExecutor(o,c).execute(run,step="bad",request="request",success_state=RunState.COMPLETE)
    assert o.calls == 0


def test_playbook_can_create_and_strengthen_component_gap(tmp_path: Path):
    from component_engineering import ComponentEngineeringService, EngineeringRequestKind, EngineeringRisk, FileComponentEngineeringStore
    from playbook_coordinator import PlaybookRunCoordinator
    run_store=FilePlaybookRunStore(tmp_path/'runs')
    eng=ComponentEngineeringService(FileComponentEngineeringStore(tmp_path/'engineering'))
    c=PlaybookRunCoordinator(run_store,eng)
    run=c.ensure_run(identity=PlaybookIdentity('disk_space_alert','0.1.0'),run_id='run-1',ticket_id='T1',company_id='C1',device_id='D1')
    req,created=c.report_component_gap(run,problem_key='disk-space:machine-readable-largest-files',title='Improve disk evidence output',kind=EngineeringRequestKind.IMPROVE_EXISTING,risk=EngineeringRisk.READ_ONLY,desired_capability='Return bounded largest files/folders summary',gap_summary='Current playbook cannot safely identify cleanup candidates.',evidence_refs=('ev-1',),existing_component_name='DattoSize')
    assert created is True and req.source_run_ids==['run-1'] and req.source_ticket_ids==['T1']
    restored=c.store.load('run-1')
    assert restored.metadata['component_engineering_request_id']==req.request_id
    assert restored.completed_steps[-1].status=='created'
    req2,created=c.report_component_gap(restored,problem_key='disk-space:machine-readable-largest-files',title='Same gap',kind=EngineeringRequestKind.IMPROVE_EXISTING,risk=EngineeringRisk.READ_ONLY,desired_capability='same',gap_summary='Repeated same gap.',evidence_refs=('ev-2',))
    assert created is False and req2.occurrence_count==2
