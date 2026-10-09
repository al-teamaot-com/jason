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
