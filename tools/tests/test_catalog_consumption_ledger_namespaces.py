"""Root bootstrap + MCP approval namespaces share a durable ledger, never authority."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from tools import catalog_scoped_promotion_host as p

BOOTSTRAP='catalog-root-owner-'+'a'*32
MCP='owner-mcp-'+'b'*32
SOURCE='1'*40
PLAN='2'*64
OWNER='bee80bdc-ffb0-4c50-b453-c09d4d411f5f'


def put(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True)+'\n')
    return path


@pytest.fixture
def host(tmp_path,monkeypatch):
    state=tmp_path/'root'
    consumed=state/'consumed-owner-approvals'
    consumed.mkdir(parents=True)
    consumed.chmod(0o700)
    host=p.NativeCatalogHost.__new__(p.NativeCatalogHost)
    host.root=state
    orig=Path.stat
    def trusted_directory_uid(path,*args,**kwargs):
        actual=orig(path,*args,**kwargs)
        if path==consumed:
            return SimpleNamespace(st_mode=actual.st_mode,st_uid=0)
        return actual
    monkeypatch.setattr(Path,'stat',trusted_directory_uid)
    monkeypatch.setattr(p,'secure_read',lambda path,**kw: Path(path).read_bytes())
    record={
        'schema_version':'1.0','action':'catalog_root_install_only_v1',
        'approval_id':BOOTSTRAP,'source_sha':SOURCE,
        'plan_sha256':PLAN,'owner_oid':OWNER,
        'consumed_at':'2026-11-19T17:00:00Z','one_use':True,
    }
    audit={
        'status':'exact_catalog_root_install_verified',
        'action':'catalog_root_install_only_v1',
        'approval_id':BOOTSTRAP,'source_sha':SOURCE,
        'plan_sha256':PLAN,'verified_owner_oid':OWNER
    }
    put(consumed/(BOOTSTRAP+'.json'),record)
    put(state/'root-installer-audit'/('release-'+SOURCE[:16]+'.json'),audit)
    return host,consumed,record,audit


def test_valid_root_bootstrap_consumption_is_preserved_and_not_mcp_approval(host):
    instance,consumed,_,_=host
    assert instance.consumed_approval_ids()==frozenset()
    assert (consumed/(BOOTSTRAP+'.json')).exists()


def test_real_mcp_consumption_is_only_returned_replay_id(host):
    instance,consumed,_,_=host
    put(consumed/(MCP+'.json'),{
        'schema_version':'1.0','approval_id':MCP,
        'release_id':'release-'+'c'*16,
        'consumed_at':'2026-11-19T17:01:00Z','one_use':True,
    })
    assert instance.consumed_approval_ids()==frozenset({MCP})
    assert (consumed/(BOOTSTRAP+'.json')).exists()


@pytest.mark.parametrize('filename',[
    'README','unexpected.tmp','.DS_Store','catalog-owner-'+'e'*32+'.json',
    'owner-mcp-'+'f'*32+'.txt',
])
def test_unreviewed_entry_denied_without_removing_evidence(host,filename):
    instance,consumed,_,_=host
    (consumed/filename).write_text('unreviewed')
    with pytest.raises(PermissionError,match='CONSUMPTION_LEDGER_UNEXPECTED_FILE'):
        instance.consumed_approval_ids()
    assert (consumed/filename).exists()


@pytest.mark.parametrize('key,value',[
    ('action','catalog_scope_promote'),
    ('approval_id','owner-mcp-'+'0'*32),
    ('plan_sha256','d'*64),
    ('source_sha','e'*40),
    ('owner_oid','other'),
    ('one_use',False),
])
def test_bootstrap_record_tampering_denied(host,key,value):
    instance,consumed,record,_=host
    record[key]=value
    put(consumed/(BOOTSTRAP+'.json'),record)
    with pytest.raises(PermissionError,match='CONSUMPTION_LEDGER_ROOT_BOOTSTRAP|ROOT_AUDIT_INVALID'):
        instance.consumed_approval_ids()


def test_valid_looking_bootstrap_record_rejected_when_original_audit_drifts(host):
    instance,consumed,_,audit=host
    audit['verified_owner_oid']='c848022d-e13b-4457-84b0-e2f5c00dcaf6'
    put(instance.root/'root-installer-audit'/('release-'+SOURCE[:16]+'.json'),audit)
    with pytest.raises(PermissionError,match='CONSUMPTION_LEDGER_ROOT_BOOTSTRAP_AUDIT_DRIFT'):
        instance.consumed_approval_ids()


def test_orphan_bootstrap_record_rejected(host):
    instance,consumed,_,_=host
    (instance.root/'root-installer-audit'/('release-'+SOURCE[:16]+'.json')).unlink()
    with pytest.raises(PermissionError,match='ROOT_AUDIT_INVALID'):
        instance.consumed_approval_ids()


def test_two_bootstrap_records_denied(host):
    instance,consumed,record,_=host
    other='catalog-root-owner-'+'f'*32
    record=dict(record,approval_id=other)
    put(consumed/(other+'.json'),record)
    with pytest.raises(PermissionError,match='CONSUMPTION_LEDGER_ROOT_BOOTSTRAP_'):
        instance.consumed_approval_ids()


@pytest.mark.parametrize('field,value',[
    ('approval_id','owner-mcp-'+'f'*32),
    ('release_id','unreviewed-release'),
    ('one_use',False),
])
def test_mcp_ledger_record_scope_cannot_be_forged(host,field,value):
    instance,consumed,_,_=host
    doc={'schema_version':'1.0','approval_id':MCP,
         'release_id':'release-'+'c'*16,'one_use':True,
         'consumed_at':'2026-11-19T17:01:00Z'}
    doc[field]=value
    put(consumed/(MCP+'.json'),doc)
    with pytest.raises(PermissionError,match='CONSUMPTION_LEDGER_MCP_PROOF_INVALID'):
        instance.consumed_approval_ids()
