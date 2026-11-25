"""No provider or GitHub writes: prove safe handoff and no competing lanes."""
from __future__ import annotations
import fcntl
import json
import os
import subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import independent_governed_lane as m

NOW=datetime(2026,11,4,15,0,tzinfo=timezone.utc)


def fixture(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    installed=tmp_path/'installed';installed.mkdir()
    spool=tmp_path/'spool';spool.mkdir(mode=0o700)
    lock=tmp_path/'production.lock';lock.write_text('release lock\n');lock.chmod(0o600)
    receipt=spool/'pmv3-engineering-owner-pause.json';receipt.write_text('{"status":"paused_by_owner"}')
    dropin=tmp_path/'owner-pause.conf';dropin.write_text('[Unit]\n'+m.LEGACY_PAUSE_DIRECTIVE+'\n')
    subprocess.run(['git','init','-q'],cwd=repo,check=True,capture_output=True)
    subprocess.run(['git','config','user.name','Stage Test'],cwd=repo,check=True)
    subprocess.run(['git','config','user.email','test@example.invalid'],cwd=repo,check=True)
    tools=repo/'tools';tools.mkdir()
    for name,_,_ in m.LANES.values():
        (tools/name).write_text('print("synthetic native worker")\n')
        (installed/name).write_bytes((tools/name).read_bytes())
    subprocess.run(['git','add','.'],cwd=repo,check=True,capture_output=True)
    subprocess.run(['git','commit','-qm','baseline'],cwd=repo,check=True,capture_output=True)
    return repo,installed,spool,lock,receipt,dropin


def execute(lane,fixtures,runner):
    repo,installed,spool,lock,receipt,dropin=fixtures
    return m.execute(lane,repo=repo,installed=installed,spool=spool,
                     production_lock=lock,pause_receipt=receipt,legacy_guard=dropin,
                     legacy_probe=lambda:True,runner=runner)


def test_native_support_then_dependent_lanes_have_fixed_verified_worker_calls(tmp_path):
    fixtures=fixture(tmp_path);calls=[]
    def runner(command,**kwargs):
        calls.append(tuple(command))
        assert kwargs['timeout'] in (600,1200,4500)
        assert kwargs['check'] is False
        return SimpleNamespace(returncode=0)
    assert execute('support',fixtures,runner)['status']=='succeeded'
    assert execute('todo-intake',fixtures,runner)['status']=='succeeded'
    assert execute('development',fixtures,runner)['status']=='succeeded'
    assert len(calls)==3
    assert any('support_repair_host_worker.py' in c[1] for c in calls)
    assert all('--repo' in c and '--spool' in c for c in calls)


def test_development_cannot_run_before_successful_support(tmp_path):
    fixtures=fixture(tmp_path)
    called=[]
    result=execute('development',fixtures,lambda *a,**k:called.append(a))
    assert result['status']=='deferred' and result['reason']=='missing_successful_support_pass'
    assert called==[]


def test_worker_failure_persists_and_dependent_lanes_defer(tmp_path):
    fixtures=fixture(tmp_path)
    failed=execute('support',fixtures,lambda *a,**k:SimpleNamespace(returncode=12))
    assert failed['status']=='worker_failed' and failed['return_code']==12
    result=execute('todo-intake',fixtures,lambda *a,**k:pytest.fail('worker should not run'))
    assert result['status']=='deferred'
    assert result['reason']=='support_result_failed_or_revision_mismatch'


def test_production_transaction_exclusive_lock_defers_without_worker_call(tmp_path):
    fixtures=fixture(tmp_path);lock=fixtures[3]
    with lock.open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=execute('support',fixtures,lambda *a,**k:pytest.fail('must defer'))
        assert result['status']=='deferred' and result['reason']=='production_transaction_busy'
        fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def test_independent_support_lock_prevents_parallel_claims(tmp_path):
    fixtures=fixture(tmp_path);spool=fixtures[2]
    path=spool/'independent-engineering-lanes.lock'
    path.touch(mode=0o600);path.chmod(0o600)
    with path.open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=execute('support',fixtures,lambda *a,**k:pytest.fail('must defer'))
        assert result['status']=='deferred' and result['reason']=='engineering_lane_busy'
        supervisor=execute('supervisor',fixtures,lambda *a,**k:SimpleNamespace(returncode=0))
        assert supervisor['status']=='succeeded'
        fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def test_tampered_worker_source_rejected_before_execution(tmp_path):
    fixtures=fixture(tmp_path);installed=fixtures[1]
    (installed/m.LANES['support'][0]).write_text('tampered')
    with pytest.raises(m.LaneError,match='differs'):
        execute('support',fixtures,lambda *a,**k:pytest.fail('must deny'))


def test_owner_pause_absence_denies_new_lane(tmp_path):
    fixtures=fixture(tmp_path);fixtures[4].unlink()
    with pytest.raises(m.LaneError,match='owner-paused'):
        execute('support',fixtures,lambda *a,**k:pytest.fail('must deny'))


def test_stale_future_revision_mismatched_support_dependency_denied():
    receipt={'observed_at':NOW.isoformat(),'status':'succeeded','source_revision':'a'*40}
    assert m.support_dependency('development',receipt,revision='a'*40,now=NOW)=='allowed'
    assert m.support_dependency('development',receipt,revision='b'*40,now=NOW)=='support_result_failed_or_revision_mismatch'
    assert m.support_dependency('development',receipt,revision='a'*40,now=NOW+timedelta(minutes=20))=='support_result_stale_or_invalid'
    receipt['observed_at']=(NOW+timedelta(minutes=20)).isoformat()
    assert m.support_dependency('todo-intake',receipt,revision='a'*40,now=NOW)=='support_result_stale_or_invalid'


def test_worker_receipts_do_not_claim_provider_authority(tmp_path):
    fixtures=fixture(tmp_path)
    result=execute('support',fixtures,lambda *a,**k:SimpleNamespace(returncode=0))
    assert result['advisory_only'] is True
    assert result['production_authority'] is False
    assert 'provider_write' not in result
    assert json.loads((fixtures[2]/'independent-lane-support.json').read_text())['source_revision']==result['source_revision']


def test_old_controller_guard_absent_or_invalid_blocks_new_worker(tmp_path):
    fixtures=fixture(tmp_path)
    fixtures[5].unlink()
    with pytest.raises(m.LaneError,match='guard not verified'):
        execute('support',fixtures,lambda *a,**k:pytest.fail('must not run'))
    fixtures[5].write_text('[Unit]\nConditionPathExists=/tmp/not-our-pause.json\n')
    with pytest.raises(m.LaneError,match='no-start condition missing'):
        execute('support',fixtures,lambda *a,**k:pytest.fail('must not run'))


def test_live_legacy_controller_active_blocks_new_lanes(tmp_path):
    fixtures=fixture(tmp_path)
    with pytest.raises(m.LaneError,match='not verified inactive'):
        m.execute('support',repo=fixtures[0],installed=fixtures[1],spool=fixtures[2],
          production_lock=fixtures[3],pause_receipt=fixtures[4],legacy_guard=fixtures[5],
          legacy_probe=lambda:False,runner=lambda *a,**k:pytest.fail('must not run'))


def test_native_old_controller_probe_requires_inactive_and_no_condition():
    def fake(stdout):
        def runner(args,**kwargs):
            assert args[:3]==['systemctl','--user','show']
            return SimpleNamespace(returncode=0,stdout=stdout)
        return runner
    assert m.loaded_old_controller_paused(fake('ActiveState=inactive\nConditionResult=no\n')) is True
    assert m.loaded_old_controller_paused(fake('ActiveState=active\nConditionResult=no\n')) is False
    assert m.loaded_old_controller_paused(fake('ActiveState=inactive\nConditionResult=yes\n')) is False
