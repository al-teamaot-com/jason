from pathlib import Path
import pytest
from component_engineering import ComponentEngineeringService, EngineeringRequestKind, EngineeringRisk, EngineeringLifecycle, FileComponentEngineeringStore


def test_report_gap_creates_then_strengthens_same_request(tmp_path: Path):
    svc=ComponentEngineeringService(FileComponentEngineeringStore(tmp_path))
    one,created=svc.report_gap(problem_key='disk-space:largest-files-output',title='Improve disk usage evidence',kind=EngineeringRequestKind.IMPROVE_EXISTING,risk=EngineeringRisk.READ_ONLY,desired_capability='Return bounded machine-readable largest folders/files',gap_summary='Current evidence only confirms threshold.',playbook_id='disk_space_alert',run_id='r1',ticket_id='T1',evidence_refs=('e1',),existing_component_uid='u1',existing_component_name='Existing')
    assert created is True and one.occurrence_count==1
    two,created=svc.report_gap(problem_key='disk-space:largest-files-output',title='ignored duplicate title',kind=EngineeringRequestKind.IMPROVE_EXISTING,risk=EngineeringRisk.READ_ONLY,desired_capability='same',gap_summary='Repeated gap confirmed.',playbook_id='disk_space_alert',run_id='r2',ticket_id='T2',evidence_refs=('e2',))
    assert created is False and two.request_id==one.request_id and two.occurrence_count==2
    assert two.source_run_ids==['r1','r2'] and two.evidence_refs==['e1','e2']


def test_duplicate_active_problem_keys_fail_closed(tmp_path: Path):
    svc=ComponentEngineeringService(FileComponentEngineeringStore(tmp_path))
    a,_=svc.report_gap(problem_key='same',title='A',kind=EngineeringRequestKind.NEW_COMPONENT,risk=EngineeringRisk.READ_ONLY,desired_capability='x',gap_summary='gap')
    b=svc.store.load(a.request_id); b.request_id='CER-second'; svc.store.save(b)
    with pytest.raises(ValueError,match='multiple active'):
        svc.report_gap(problem_key='same',title='X',kind=EngineeringRequestKind.NEW_COMPONENT,risk=EngineeringRisk.READ_ONLY,desired_capability='x',gap_summary='gap')


def test_terminal_request_cannot_be_strengthened(tmp_path: Path):
    svc=ComponentEngineeringService(FileComponentEngineeringStore(tmp_path))
    req,_=svc.report_gap(problem_key='x',title='X',kind=EngineeringRequestKind.NEW_COMPONENT,risk=EngineeringRisk.READ_ONLY,desired_capability='x',gap_summary='gap')
    req.set_lifecycle(EngineeringLifecycle.RESOLVED); svc.store.save(req)
    new,created=svc.report_gap(problem_key='x',title='X2',kind=EngineeringRequestKind.NEW_COMPONENT,risk=EngineeringRisk.READ_ONLY,desired_capability='x',gap_summary='new occurrence')
    assert created is True and new.request_id=='CER-x'


def test_path_traversal_rejected(tmp_path: Path):
    store=FileComponentEngineeringStore(tmp_path)
    with pytest.raises(ValueError,match='invalid'):
        store.load('../x')
