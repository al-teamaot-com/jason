from pathlib import Path
import pytest
from completion_gap_router import CompletionGapRouter,FileCompletionGapStore,GapClass
from playbook_runtime import FilePlaybookRunStore,PlaybookRunRecord,RunState

def setup(tmp_path):
 runs=FilePlaybookRunStore(tmp_path/'runs'); r=PlaybookRunRecord(run_id='r1',playbook_id='p1',playbook_version='1',ticket_id='T1',company_id='C1',state=RunState.DIAGNOSING); runs.create(r); return CompletionGapRouter(FileCompletionGapStore(tmp_path/'gaps'),runs),r

def test_provider_gap_routes_and_deduplicates(tmp_path):
 router,r=setup(tmp_path); g,new=router.route(r,problem_key='provider:missing-write',gap_class=GapClass.PROVIDER_CAPABILITY,title='Need write capability',summary='Supported provider write is missing',evidence_refs=('e1',)); assert new and g.route_target=='capability_backlog' and r.state==RunState.BLOCKED
 r2=PlaybookRunRecord(run_id='r2',playbook_id='p1',playbook_version='1',ticket_id='T2',company_id='C1',state=RunState.DIAGNOSING); router.runs.create(r2); g2,new=router.route(r2,problem_key='provider:missing-write',gap_class=GapClass.PROVIDER_CAPABILITY,title='same',summary='same',evidence_refs=('e2',)); assert not new and g2.occurrence_count==2 and g2.run_ids==['r1','r2']

def test_temporary_condition_requires_and_schedules_recheck(tmp_path):
 router,r=setup(tmp_path)
 with pytest.raises(ValueError,match='recheck'): router.route(r,problem_key='offline',gap_class=GapClass.TEMPORARY_CONDITION,title='Offline',summary='Endpoint offline')
 g,_=router.route(r,problem_key='offline',gap_class=GapClass.TEMPORARY_CONDITION,title='Offline',summary='Endpoint offline',recheck_at='2026-09-20T13:00:00Z'); assert g.next_recheck_at and r.state==RunState.RECHECK_PENDING

def test_human_decision_is_waiting_not_authorized(tmp_path):
 router,r=setup(tmp_path); g,_=router.route(r,problem_key='decision:x',gap_class=GapClass.HUMAN_DECISION,title='Need owner decision',summary='Ambiguous business choice'); assert g.lifecycle.value=='waiting' and r.blocked_reason_class=='human_decision_required'


def test_reason_classification_is_deterministic_and_unknown_fails_closed(tmp_path):
    from completion_gap_router import classify_reason_class
    assert classify_reason_class('component_output_inadequate') == GapClass.COMPONENT_TOOLING
    assert classify_reason_class('approved_template_missing') == GapClass.COMMUNICATION_TEMPLATE
    assert classify_reason_class('documentation_missing') == GapClass.DOCUMENTATION
    assert classify_reason_class('endpoint_offline') == GapClass.TEMPORARY_CONDITION
    with pytest.raises(ValueError,match='unrecognized'):
        classify_reason_class('mystery_blocker')
