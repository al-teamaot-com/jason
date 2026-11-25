"""Canary output normalization; synthetic receipts, no provider execution."""
import json
import pytest
from jason_runtime.deb_canary_evidence import DebCanaryEvidenceError, reduce_deb_canary


def receipt(capability, data):
    return {"status":"succeeded", "capability":capability, "correlation_id":"synthetic",
            "evidence":{"provider":"datto_rmm", "warnings":[], "data":data}}


def fixture():
    payload={"mode":"native_readonly_canary", "source_state":"AlreadyMatched",
             "service_state":"RunningOriginalPairing", "original_registration_verified":True,
             "changed":False, "installer_executed":False, "backup_started":False,
             "production_acceptance_complete":False}
    args=dict(job_uid="job",device_uid="device",component_uid="component",
        job_receipt=receipt("automation.job.read",{
            "job":{"resource_id":"job","status":"completed"},"discovery_complete":True}),
        stdout_receipt=receipt("automation.job.output.read",{
            "resource_id":"job","device_uid":"device","component_uid":"component",
            "stream":"stdout","outputs":[{"component_uid":"component","stream":"stdout",
                "text":"","truncated":False}],"match_count":1,
            "output_bounded":False,"discovery_complete":True}))
    return args,payload


def run(args,payload):
    args['stdout_receipt']['evidence']['data']['outputs'][0]['text']=json.dumps(payload)
    return reduce_deb_canary(**args)


def test_exact_success_reduces_to_observations_and_never_execution_authority():
    args,p=fixture();r=run(args,p)
    assert r['native_source_and_registration_verified']
    assert not r['source_alias_missing']
    assert not r['provider_mutation_allowed'] and not r['production_acceptance_complete']
    assert len(r['native_canary_evidence_sha256'])==64
    assert not any('approval' in k or 'grant' in k for k in r)


def test_missing_alias_or_stopped_agent_never_becomes_automatic_repair():
    a,p=fixture();p['source_state']='WouldCreate';p['service_state']='WouldStartService';p['original_registration_verified']=False
    r=run(a,p)
    assert r['source_alias_missing'] and r['existing_agent_stopped']
    assert not r['native_source_and_registration_verified']
    assert not r['provider_mutation_allowed']


@pytest.mark.parametrize('key',['job_uid','device_uid','component_uid'])
def test_changed_read_selectors_reject(key):
    a,p=fixture();a[key]='different'
    with pytest.raises(DebCanaryEvidenceError):run(a,p)


@pytest.mark.parametrize('variation',['denied','wrong-capability','wrong-provider','warning','incomplete','pending','missing-output','multiple-output','truncated','bounded'])
def test_failed_or_uncertain_job_output_is_not_success(variation):
    a,p=fixture();o=a['stdout_receipt'];d=o['evidence']['data']
    if variation=='denied':o['status']='failed'
    elif variation=='wrong-capability':o['capability']='other.read'
    elif variation=='wrong-provider':o['evidence']['provider']='other'
    elif variation=='warning':o['evidence']['warnings']=['partial']
    elif variation=='incomplete':d['discovery_complete']=False
    elif variation=='pending':a['job_receipt']['evidence']['data']['job']['status']='active'
    elif variation=='missing-output':d['match_count']=0
    elif variation=='multiple-output':d['match_count']=2
    elif variation=='truncated':d['outputs'][0]['truncated']=True
    elif variation=='bounded':d['output_bounded']=True
    with pytest.raises(DebCanaryEvidenceError):run(a,p)


@pytest.mark.parametrize('key,value',[
    ('changed',True),('installer_executed',True),('backup_started',True),
    ('production_acceptance_complete',True),('changed',0),
    ('source_state','Created'),('service_state','Restarted'),
    ('original_registration_verified',False),('unexpected_secret','never-persist')])
def test_schema_drift_contradiction_or_modification_rejects(key,value):
    a,p=fixture();p[key]=value
    with pytest.raises(DebCanaryEvidenceError):run(a,p)


def test_ordinary_service_read_is_not_canary_acceptance():
    a,_=fixture()
    a['stdout_receipt']['evidence']['data']['outputs'][0]['text']='{"Name":"DattoBackupAgentService","Status":4,"StartType":2}'
    with pytest.raises(DebCanaryEvidenceError):reduce_deb_canary(**a)


@pytest.mark.parametrize('variation', ['trailing-failure', 'leading-warning', 'duplicate-key', 'invalid-json', 'array', 'multiple-json', 'structured-source', 'structured-service'])
def test_ambiguous_or_contaminated_stdout_cannot_mask_failed_canary(variation):
    a,p=fixture()
    if variation=='structured-source':p['source_state']=[]
    if variation=='structured-service':p['service_state']={}
    text=json.dumps(p)
    if variation=='trailing-failure':text+='\nDEB_NATIVE_READONLY_CANARY_FAILED_CLOSED'
    elif variation=='leading-warning':text='unexpected diagnostic\n'+text
    elif variation=='duplicate-key':text=text[:-1]+',"changed":true,"changed":false}'
    elif variation=='invalid-json':text='{broken'
    elif variation=='array':text='[]'
    elif variation=='multiple-json':text+='\n'+text
    a['stdout_receipt']['evidence']['data']['outputs'][0]['text']=text
    with pytest.raises(DebCanaryEvidenceError):reduce_deb_canary(**a)


def test_real_connector_normalization_preserves_required_job_and_output_binding():
    from connectors.datto_rmm.automation_reads import DattoRmmAutomationReadConnector
    a,p=fixture()
    a['job_receipt']['evidence']['data']=DattoRmmAutomationReadConnector._canonical_job_read_result(
        payload={'uid':'job','status':'completed'}, arguments={'resource_id':'job'})
    a['stdout_receipt']['evidence']['data']=DattoRmmAutomationReadConnector._canonical_job_output_result(
        payload=[{'componentUid':'other','stdData':'unrelated output'},
                 {'componentUid':'component','stdData':json.dumps(p)}],
        arguments={'resource_id':'job','device_uid':'device','component_uid':'component','stream':'stdout'})
    assert reduce_deb_canary(**a)['native_source_and_registration_verified'] is True
