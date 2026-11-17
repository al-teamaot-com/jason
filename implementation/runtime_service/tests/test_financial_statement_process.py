import json
import sqlite3
from pathlib import Path
import pytest
from jason_runtime import financial_statement_process as p

TENANT='00000000-0000-0000-0000-000000000001'

def config(tmp_path):
    return dict(enabled=False,tenant_id=TENANT,drive_id='approved-drive',
        root_path='Bank Checking Accounts Register',timezone='America/New_York',run_hour=5,
        boundary_snapshot=str(tmp_path/'boundary.sqlite3'),openbao_url='http://openbao:8200',
        role_id_path='/run/secrets/role_id',secret_id_path='/run/secrets/secret_id')

def test_disabled_process_does_not_build_worker_or_contact_provider(tmp_path,monkeypatch):
    path=tmp_path/'config.json';path.write_text(json.dumps(config(tmp_path)))
    monkeypatch.setattr(p,'build_worker',lambda *_:pytest.fail('must not build disabled writer'))
    assert p.main(['--config',str(path)]) is None

@pytest.mark.parametrize('key,value',[('root_path','other'),('run_hour',True),('tenant_id','invalid'),('enabled','true')])
def test_rejects_unreviewed_or_malformed_config(tmp_path,key,value):
    cfg=config(tmp_path);cfg[key]=value
    path=tmp_path/'config.json';path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):p.load_config(path)

def test_boundary_validation_and_copy_preserve_source(tmp_path,monkeypatch):
    cfg=config(tmp_path);source=Path(cfg['boundary_snapshot'])
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE client_boundaries (external_tenant_id TEXT, profile TEXT, status TEXT, provider TEXT)')
        c.execute('INSERT INTO client_boundaries VALUES (?,?,?,?)',(TENANT,'sharepoint-write','validated','microsoft_sharepoint'))
    before=source.read_bytes();state=tmp_path/'state';state.mkdir()
    captured={}
    monkeypatch.setattr(p,'build_financial_statement_maintenance',lambda **kw:captured.update(kw) or object())
    p.build_worker(cfg,state)
    assert source.read_bytes()==before
    assert captured['boundary_db']==state/'boundary.sqlite3'
    assert captured['state_db']==state/'maintenance.sqlite3'
    assert captured['audit'] is not None

@pytest.mark.parametrize('status,profile',[('pending','sharepoint-write'),('validated','directory-read')])
def test_invalid_boundary_denies_writer_construction(tmp_path,status,profile):
    cfg=config(tmp_path)
    with sqlite3.connect(cfg['boundary_snapshot']) as c:
        c.execute('CREATE TABLE client_boundaries (external_tenant_id TEXT, profile TEXT, status TEXT, provider TEXT)')
        c.execute('INSERT INTO client_boundaries VALUES (?,?,?,?)',(TENANT,profile,status,'microsoft_sharepoint'))
    state=tmp_path/'state';state.mkdir()
    with pytest.raises(ValueError,match='validated'):p.build_worker(cfg,state)

class ReadOnlyClient:
    def get_item_by_path(self,**_):return {'id':'approved-root','folder':{}}
    def list_children(self,**_):return []
    def create_folder(self,**_):pytest.fail('preflight mutated provider')
    def move_and_rename(self,**_):pytest.fail('preflight mutated provider')

def test_preflight_is_provider_read_only():
    class Worker:
        client=ReadOnlyClient();tenant_id=TENANT;drive_id='drive';root_path='root'
    result=p.preflight(Worker())
    assert result['provider_mutations']==0
    assert result['scheduled_run_verified'] is False


def test_second_process_cannot_construct_writer(tmp_path,monkeypatch):
    import fcntl
    cfg=config(tmp_path);cfg['enabled']=True
    path=tmp_path/'config.json';path.write_text(json.dumps(cfg))
    state=tmp_path/'state';state.mkdir()
    monkeypatch.setattr(p,'STATE',state)
    monkeypatch.setattr(p,'build_worker',lambda *_:pytest.fail('second writer constructed'))
    with (state/'process.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):p.main(['--config',str(path)])
