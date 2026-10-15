import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

p=Path(__file__).resolve().parents[1]/'release_control_transition_worker.py'
s=importlib.util.spec_from_file_location('release_control_transition_worker',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
REV='a'*40

def test_revalidation_requires_exact_root_evidence():
    state={'schema_version':'1.0','last_known_good':{'manifest':{'revision':REV}},'circuit_breaker':{'state':'open'}}
    with patch.object(m,'verify_drift'),patch.object(m,'verify_health',return_value={'revision':REV,'complete':True}):
        output=m.apply_transition({'action':'revalidate','revision':REV},state)
    assert output['circuit_breaker']['state']=='closed'
    assert output['last_revalidation']['revision']==REV


def test_revalidation_rejects_revision_mismatch():
    state={'schema_version':'1.0','last_known_good':{'manifest':{'revision':'b'*40}}}
    with patch.object(m,'verify_drift'):
        with pytest.raises(ValueError,match='last known good'):
            m.apply_transition({'action':'revalidate','revision':REV},state)


def test_open_never_triggers_health_check():
    with patch.object(m,'verify_drift',side_effect=AssertionError('unexpected')):
        output=m.apply_transition({'action':'open','revision':REV,'reason':'rollback failure'},{'schema_version':'1.0'})
    assert output['circuit_breaker']['state']=='open'


def test_last_known_good_requires_closed_or_production_and_approval(tmp_path):
    record={'state':'closed','owner_approval':{'approved':True,'candidate_sha':REV}}
    path=tmp_path/'records'/('release-'+REV[:16]+'.json')
    path.parent.mkdir();path.write_text(json.dumps(record))
    with patch.object(m,'ROOT',tmp_path),patch.object(m,'verify_drift'),patch.object(m,'verify_health',return_value={'revision':REV,'complete':True}):
        output=m.apply_transition({'action':'set_last_known_good','revision':REV,'release_id':'release-'+REV[:16]}, {'schema_version':'1.0'})
    assert output['last_known_good']['manifest']['revision']==REV
    record['owner_approval']['approved']=False;path.write_text(json.dumps(record))
    with patch.object(m,'ROOT',tmp_path),patch.object(m,'verify_drift'):
        with pytest.raises(ValueError,match='approval'):
            m.apply_transition({'action':'set_last_known_good','revision':REV,'release_id':'release-'+REV[:16]}, {'schema_version':'1.0'})


def test_root_transition_accepts_only_verified_authorized_retry(tmp_path):
    base='release-'+REV[:16]
    retry=base+'-retry-1'
    root=tmp_path/'records';root.mkdir()
    historical={'state':'rolled_back','failure':{'rollback_verified':True},
                'release_candidate':{'candidate_sha':REV}}
    candidate={'state':'production','reissued_from':base,
       'release_candidate':{'candidate_sha':REV},
       'owner_approval':{'approved':True,'candidate_sha':REV}}
    (root/(base+'.json')).write_text(json.dumps(historical))
    (root/(retry+'.json')).write_text(json.dumps(candidate))
    req={'action':'set_last_known_good','revision':REV,'release_id':retry}
    with patch.object(m,'ROOT',tmp_path),patch.object(m,'verify_drift'),patch.object(m,'verify_health',return_value={'revision':REV,'complete':True}):
        output=m.apply_transition(req,{'schema_version':'1.0'})
        assert output['last_known_good']['release_id']==retry
        candidate['owner_approval']['approved']=False
        (root/(retry+'.json')).write_text(json.dumps(candidate))
        with pytest.raises(ValueError,match='approval'):
            m.apply_transition(req,{'schema_version':'1.0'})
        historical['failure']['rollback_verified']=False
        (root/(base+'.json')).write_text(json.dumps(historical))
        with pytest.raises(ValueError,match='historical rollback'):
            m.apply_transition(req,{'schema_version':'1.0'})


def test_stale_root_drift_regenerated_only_by_clean_independent_guard(tmp_path):
    from datetime import datetime, timezone, timedelta
    from types import SimpleNamespace
    stale={'schema_version':'1.0','status':'pass','problems':[],
           'observed_at':(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()}
    fresh={'schema_version':'1.0','status':'pass','problems':[],
           'observed_at':datetime.now(timezone.utc).isoformat()}
    policy=tmp_path/'policy.json';policy.write_text('{}')
    guard=tmp_path/'guard.py';guard.write_text('pass')
    from unittest.mock import patch
    with patch.object(m,'DRIFT_CONFIG',policy),patch.object(m,'DRIFT_EVALUATOR',guard), \
         patch.object(m,'protected_read',side_effect=[stale,fresh]) as read, \
         patch.object(m,'write_json') as write, \
         patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(fresh))):
        # Mock root metadata for sandbox test fixture only.
        with patch.object(m.Path,'stat',return_value=SimpleNamespace(st_mode=0o100600,st_uid=0)):
            m.verify_drift()
    assert read.call_count==2
    write.assert_called_once_with(m.DRIFT,fresh,0,0)


def test_stale_root_drift_refresh_rejects_failed_guard(tmp_path):
    from datetime import datetime, timezone, timedelta
    from types import SimpleNamespace
    stale={'schema_version':'1.0','status':'pass','problems':[],
           'observed_at':(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()}
    policy=tmp_path/'policy.json';policy.write_text('{}')
    guard=tmp_path/'guard.py';guard.write_text('pass')
    with patch.object(m,'DRIFT_CONFIG',policy),patch.object(m,'DRIFT_EVALUATOR',guard), \
         patch.object(m,'protected_read',return_value=stale), \
         patch.object(m,'write_json') as write, \
         patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=2,stdout='')):
        with patch.object(m.Path,'stat',return_value=SimpleNamespace(st_mode=0o100600,st_uid=0)):
            with pytest.raises(ValueError,match='did not pass'):
                m.verify_drift()
    write.assert_not_called()
