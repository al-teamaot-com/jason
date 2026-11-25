"""Operational closure boundaries and exact filesystem rollback; no live calls."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json,os,stat
import pytest
from tools import pmv4_e_operational_closure as c


def manifest_pair():
    old={'complete':True,'revision':c.ROLLBACK,'runtime_image_id':'same-image',
         'mcp_image_id':'same-mcp','observed_at':'before',
         'scheduled_control_units':{'jason-self-heal-watchdog.timer':'active',
                                    c.OLD_USER[1]:'active'}}
    marker={'retired_user_units':list(c.OLD_USER),'retired_system_units':list(c.OLD_ROOT),
            'replacement_user_units':list(c.NEW_USER),'replacement_system_units':list(c.NEW_ROOT)}
    current=deepcopy(old);current['observed_at']='after'
    current['scheduled_control_units']=c.expected_schedule(old['scheduled_control_units'],marker)
    return old,current,marker


def test_lkg_recapture_allows_only_exact_accepted_scheduling_delta():
    old,current,marker=manifest_pair();c.verify_manifest_delta(old,current,marker)
    assert current['runtime_image_id']==old['runtime_image_id']
    assert set(current['scheduled_control_units'])=={*c.OLD_USER,*c.OLD_ROOT,*c.NEW_USER,*c.NEW_ROOT,'jason-self-heal-watchdog.timer'}


@pytest.mark.parametrize('fault',['runtime','foreign_timer','old_active','missing_new','new_field'])
def test_any_unrelated_fingerprint_or_scheduling_change_denies(fault):
    old,current,marker=manifest_pair()
    if fault=='runtime':current['runtime_image_id']='different-image'
    if fault=='new_field':current['unapproved_field']=True
    if fault=='foreign_timer':current['scheduled_control_units']['jason-foreign.timer']='active'
    if fault=='old_active':current['scheduled_control_units'][c.OLD_USER[0]]='active'
    if fault=='missing_new':current['scheduled_control_units'].pop(c.NEW_ROOT[0])
    with pytest.raises(c.ClosureDenied):c.verify_manifest_delta(old,current,marker)


def test_uninstalled_or_nonisolated_cli_denies_before_owner_or_host_call(monkeypatch):
    monkeypatch.setattr(c,'approved_namespace',lambda:pytest.fail('loaded authority before root boundary'))
    with pytest.raises(c.ClosureDenied,match='EXACT_ROOT_ISOLATED_REQUIRED'):
        c.main(['--source-sha','a'*40,'--apply'])


@pytest.fixture
def fs(tmp_path):
    if os.geteuid()!=0:pytest.skip('disposable UID0 filesystem fixture')
    paths=[]
    for index,name in enumerate((*c.OLD_USER,*c.OLD_ROOT)):
        path=tmp_path/name;uid=1000 if index<3 else 0;mode=0o600 if index==0 else 0o644
        c.write(path,('old-source-'+name).encode(),mode,uid)
        paths.append({'path':str(path),'uid':uid,'mode':mode,'sha256':c.digest(path.read_bytes())})
    old=tmp_path/'old-source';new=tmp_path/'reviewed-source';old.mkdir();new.mkdir()
    link=tmp_path/'source-link';link.symlink_to(old)
    state=tmp_path/'root-journal';state.mkdir(mode=0o700)
    dropin=tmp_path/'watchdog.service.d'/'closure.conf'
    scope={'trigger_before_images':paths,'engineering_link_before':str(old)}
    tx=c.Files(state,scope,link=link,dropin=dropin,new_source=new,production=False)
    return tx,paths,link,dropin,old,new


def test_exact_six_trigger_archive_and_restore_preserve_bytes_owners_and_modes(fs):
    tx,items,link,dropin,old,new=fs
    tx.apply()
    assert all(not Path(x['path']).exists() for x in items)
    assert dropin.read_bytes()==c.DROPIN_BYTES and link.resolve()==new
    assert (dropin.stat().st_uid,dropin.stat().st_gid)==(1000,1000)
    for item in items:
        archive=tx.state/'triggers'/Path(item['path']).name
        assert archive.stat().st_uid==0 and stat.S_IMODE(archive.stat().st_mode)==0o400
    tx.restore()
    assert link.resolve()==old and not dropin.exists() and not dropin.parent.exists()
    for item in items:
        p=Path(item['path']);m=p.stat()
        assert c.digest(p.read_bytes())==item['sha256']
        assert (m.st_uid,m.st_gid,stat.S_IMODE(m.st_mode))==(item['uid'],item['uid'],item['mode'])


def test_changed_trigger_denies_before_retiring_any_original_file(fs):
    tx,items,*_=fs
    p=Path(items[-1]['path']);p.write_bytes(b'changed')
    with pytest.raises(c.ClosureDenied,match='TRIGGER_CHANGED_BEFORE_ARCHIVE'):tx.apply()
    assert not tx.removed and all(Path(x['path']).exists() for x in items)


def test_partial_preparation_failure_restores_exact_owned_files(fs):
    tx,items,link,dropin,old,new=fs
    dropin.parent.mkdir(mode=0o700);os.chown(dropin.parent,1000,1000)
    dropin.write_bytes(b'foreign');os.chown(dropin,1000,1000);dropin.chmod(0o644)
    with pytest.raises(FileExistsError):tx.apply()
    tx.restore()
    assert dropin.read_bytes()==b'foreign' and link.resolve()==old
    assert all(c.digest(Path(x['path']).read_bytes())==x['sha256'] for x in items)


def test_rollback_refuses_to_overwrite_foreign_replacement(fs):
    tx,items,*_=fs;tx.apply()
    p=Path(items[-1]['path']);p.write_bytes(b'foreign')
    with pytest.raises(c.ClosureDenied,match='FOREIGN_RETIRED_TRIGGER'):tx.restore()
    assert p.read_bytes()==b'foreign'


def test_production_file_transaction_rejects_alternate_paths(tmp_path):
    with pytest.raises(c.ClosureDenied,match='PRODUCTION_PATH_OVERRIDE'):
        c.Files(tmp_path,{},link=tmp_path/'link',production=True)


def test_no_image_mutation_policy_weakening_or_direct_protected_state_writer():
    source=Path(c.__file__).read_text()
    for forbidden in ['docker restart','docker update','docker rm','docker compose',
                      'atomic_policy(',"os.replace(temp,CONTROL)","'action':'revalidate'"]:
        assert forbidden not in source
    assert 'set_last_known_good' in source
    assert 'verify_manifest_delta' in source
    assert 'owner_pause_sha256' in source


def test_exact_owner_denial_happens_before_file_transaction(monkeypatch):
    from contextlib import nullcontext
    seen=[];scope={'action':c.ACTION}
    def deny(actual):
        seen.append(actual);raise c.ClosureDenied('OWNER_DENIED')
    monkeypatch.setattr(c,'os',SimpleNamespace(geteuid=lambda:0))
    monkeypatch.setattr(c,'sys',SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(c,'approved_namespace',lambda:{'locks':nullcontext,'owner':deny})
    monkeypatch.setattr(c,'inspect',lambda *a:(scope,{},{}))
    monkeypatch.setattr(c,'Files',lambda *a:pytest.fail('mutation before Owner decision'))
    with pytest.raises(c.ClosureDenied,match='OWNER_DENIED'):c.main(['--source-sha','a'*40,'--apply'])
    assert seen==[scope]


def test_preflight_emits_scope_without_requesting_approval_or_mutating(monkeypatch,capsys):
    from contextlib import nullcontext
    scope={'action':c.ACTION}
    monkeypatch.setattr(c,'os',SimpleNamespace(geteuid=lambda:0))
    monkeypatch.setattr(c,'sys',SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(c,'approved_namespace',lambda:{'locks':nullcontext,'owner':lambda *a:pytest.fail('preflight requested approval')})
    monkeypatch.setattr(c,'inspect',lambda *a:(scope,{},{}))
    monkeypatch.setattr(c,'Files',lambda *a:pytest.fail('preflight mutated files'))
    c.main(['--source-sha','a'*40])
    assert json.loads(capsys.readouterr().out)['status']=='operational_closure_read_only_preflight_passed'
