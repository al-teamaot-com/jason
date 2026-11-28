"""Actual v1 interpreter/checkpoint tests; synthetic only, zero provider writes."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from hashlib import sha256
import json
import pytest
from jsonschema import Draft202012Validator

from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, SQLiteJsonShadowState, JsonShadowBoundaryError,
)

ROOT=Path(__file__).resolve().parents[3]
FILE=ROOT/'docs/playbooks/json/candidates/backupiq_endpoint_backup.1.4.0-rc.2.json'


def document():return validate_playbook_document(json.loads(FILE.read_text()))


def test_live_schema_semantic_graph_and_activation_invariants():
    p=json.loads(FILE.read_text())
    Draft202012Validator(json.loads((ROOT/'docs/playbooks/json/playbook-v1.schema.json').read_text())).validate(p)
    d=document()
    assert d.autonomy_activation=='shadow'
    assert len(p['standard_sections'])==23
    assert not p['engineering_readiness']['activation_allowed']
    assert not p['migration']['accepted_for_execution']
    assert p['scope']['direct_provider_access'] is False
    assert len(p['steps'])<=200
    for step in p['steps']:
        if step['type']=='remediation':
            assert step['approval_required'] is True
            assert step['retry']['max_attempts']==1
        if step.get('capability')=='backup.endpoint.asset.read':
            assert step['arguments']['company_id']=={'$fact':'company_id'}
    assert 'backup.endpoint.backup.search' not in d.capabilities


def test_exact_native_canary_manifest_binds_files_and_grants_no_authority():
    m=json.loads((ROOT/'components/deb-recovery/canary-manifest.json').read_text())
    assert m['component_uid'] is None
    assert m['global_or_site_variables']=='none'
    assert not any(m['side_effect_ceiling'].values())
    assert not m['standing_approval_created'] and not m['playbook_activation_authorized']
    for item in m['files']:
        assert sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256']
    canary=(ROOT/'components/deb-recovery/NativeReadOnlyCanary.ps1').read_text()
    assert "'DEB_CANARY_HELPER_HASH_CHANGED'" in canary
    assert canary.count('Resolve-DebMsiSource @sourceArguments')==1
    assert ' @sourceArguments -Apply' not in canary


@pytest.mark.parametrize('step',[
    'ticket_gate','endpoint_gate','provider_customer_gate','recovered_gate',
    'lower_impact_gate','lower_impact_classification','repair_authority_gate',
    'repair_health_gate','backup_request_gate','backup_accepted_gate',
    'legacy_reinstall_gate','diagnostic_job_gate','repair_job_gate',
    'backup_request_job_gate','note_gate','note_readback_gate','ticket_readback_gate'])
def test_missing_evidence_or_approval_never_reaches_action(step):
    assert JsonPlaybookInterpreter(document()).instruction(step_id=step,facts={}).step_id=='human_review'


@pytest.mark.parametrize('prefix,gate,fact',[
    ('diagnostic','diagnostic_job_gate','diagnostic_job_running_same_device_before_deadline'),
    ('repair','repair_job_gate','repair_job_running_same_device_before_deadline'),
    ('backup_request','backup_request_job_gate','backup_request_job_running_same_device_before_deadline')])
def test_pending_job_reads_existing_job_and_never_redispatches(prefix,gate,fact):
    j=JsonPlaybookInterpreter(document())
    instruction=j.instruction(step_id=gate,facts={fact:True})
    assert instruction.step_id==prefix+'_job_wait_1'
    assert instruction.step_type=='wait'
    assert j.next_step(instruction.step_id)==prefix+'_job_poll_1'
    assert j.instruction(step_id=prefix+'_job_poll_gate_5',facts={fact:True}).step_id=='human_review'


def test_old_backup_cannot_complete_and_wait_is_bounded_without_cycles():
    j=JsonPlaybookInterpreter(document())
    facts={'fresh_backup_after_remediation_and_no_current_alert':False,
           'backup_verification_wait_allowed':True}
    assert j.instruction(step_id='backup_success_gate',facts=facts).step_id=='backup_wait_01'
    assert j.instruction(step_id='backup_recheck_gate_11',facts=facts).step_id=='backup_wait_12'
    assert j.instruction(step_id='backup_recheck_gate_12',facts=facts).step_id=='human_review'
    facts['backup_verification_wait_allowed']=False
    assert j.instruction(step_id='backup_success_gate',facts=facts).step_id=='human_review'


def test_msi_zero_or_running_service_alone_cannot_prove_backup_success():
    j=JsonPlaybookInterpreter(document())
    assert j.instruction(step_id='backup_success_gate',facts={
        'installer_exit_code':0,'service_running':True}).step_id=='human_review'


def test_staging_is_immutable_and_never_activates_existing_registry(tmp_path):
    store=SQLitePlaybookRegistry(tmp_path/'isolated.sqlite3')
    try:
        payload=json.loads(FILE.read_text());row=store.stage(payload,actor='synthetic-engineering')
        assert row.state=='draft' and store.active_snapshot()[1]==()
        payload['expected_state']['backup_enabled']=False
        with pytest.raises(ValueError,match='IMMUTABLE'):store.stage(payload,actor='synthetic-engineering')
    finally:store.close()


class ExistingGovernedReadFixture:
    client_id='0'
    def __init__(self):self.calls=[]
    def execute(self,capability,arguments):
        assert capability=='backup.endpoint.asset.read'
        assert arguments['company_id']=='0'
        self.calls.append((capability,arguments))
        return {'status':'succeeded','evidence':{'fixture_only':True}}


def wait_document():
    # A suffix of the exact candidate, not a replacement interpreter/scheduler.
    p=json.loads(FILE.read_text())
    p['state_model']['entry_step']='backup_wait_01'
    keep={'verify_current_alerts','note_gate','create_note','verify_note',
          'note_readback_gate','complete_ticket','verify_ticket','ticket_readback_gate','complete','human_review'}
    p['steps']=[s for s in p['steps'] if s['id'].startswith(('backup_wait_','asset_recheck_','alert_recheck_','backup_recheck_gate_')) or s['id'] in keep]
    p['steps']=[s for s in p['steps'] if s['id']!='verify_current_alerts']
    return validate_playbook_document(p)


def test_real_shared_wait_checkpoint_resumes_once_and_rejects_caller_health(tmp_path):
    doc=wait_document();port=ExistingGovernedReadFixture()
    state=SQLiteJsonShadowState(tmp_path/'isolated-state.sqlite3')
    now=[datetime(2026,11,23,13,tzinfo=timezone.utc)]
    runner=GovernedJsonShadowIntegration(document=doc,state=state,read_port=port,
        read_capabilities=frozenset({'backup.endpoint.asset.read'}),
        normalize=lambda *a:{},clock=lambda:now[0])
    # Test only the wait boundary: generated read selectors deliberately require
    # trusted normalized company/asset facts, which caller seed may not supply.
    kwargs=dict(run_id='synthetic-run',client_id='0',target_id='synthetic-ticket',
                trusted_seed={'client_id':'0','target_id':'synthetic-ticket'})
    try:
        first=runner.run(**kwargs)
        assert first.status=='waiting' and not port.calls
        assert runner.run(**kwargs)==first
        assert not port.calls
        now[0]+=timedelta(minutes=15)
        resumed=runner.run(**kwargs)
        assert resumed.status=='failed_closed' and not port.calls
        assert runner.run(**kwargs)==resumed
        with pytest.raises(JsonShadowBoundaryError,match='SEED_FACTS_NOT_TRUSTED'):
            runner.run(**{**kwargs,'run_id':'injected',
                'trusted_seed':{**kwargs['trusted_seed'],'company_id':'0','service_running':True}})
    finally:state.close()
