import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'install_release_readback_policy_recovery.py'
spec=importlib.util.spec_from_file_location('install_release_readback_policy_recovery',SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def baseline():
    return {'schema_version':'1.0','required_system_units':['a.timer'], 'allowed_system_units':['b.service'], 'max_stopped_rollback_containers':20}


def test_exact_two_unit_addition_only():
    old=baseline()
    new={**old,'required_system_units':['a.timer','jason-release-control-readback.timer'], 'allowed_system_units':['b.service','jason-release-control-readback.service']}
    m.checked_candidate(old,new)
    with pytest.raises(ValueError):
        m.checked_candidate(old,{**new,'max_stopped_rollback_containers':100})
    with pytest.raises(ValueError):
        m.checked_candidate(old,{**new,'allowed_system_units':new['allowed_system_units']+['bad.service']})
    with pytest.raises(ValueError):
        m.checked_candidate(old,{**new,'required_system_units':['jason-release-control-readback.timer']})


def test_dry_run_requires_no_root(tmp_path):
    old=baseline()
    new={**old,'required_system_units':['a.timer','jason-release-control-readback.timer'], 'allowed_system_units':['b.service','jason-release-control-readback.service']}
    path=tmp_path/'config'/'production-desired-state.json'
    path.parent.mkdir();import json;path.write_text(json.dumps(old))
    with patch.object(m,'CURRENT',tmp_path),patch.object(m,'source_policy',return_value=new),patch.object(m.os,'geteuid',return_value=1000):
        m.install('a'*40,dry_run=True)
