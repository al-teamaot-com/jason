"""Exact catalog root-worker routing: reject all ambient caller authority."""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import release_host_reconcile_worker as w
from tools.catalog_scoped_promotion import ADMISSION_RECEIPT_SHA256

SHA='a'*40
RELEASE='release-'+ 'b'*16

@pytest.fixture(autouse=True)
def ci_only_owner_account(monkeypatch):
    """Only on generic CI without the production al account, simulate UID."""
    original=w.pwd.getpwnam
    try:
        original('al')
    except KeyError:
        monkeypatch.setattr(w.pwd,'getpwnam',lambda user:(
            SimpleNamespace(pw_uid=os.getuid()) if user=='al'
            else original(user)))


def request(action='catalog_scope_stage'):
    r={'schema_version':'1.0','request_id':'1'*32,
       'source_revision':SHA,'action':action,'release_id':RELEASE,
       'admission_receipt_sha256':ADMISSION_RECEIPT_SHA256}
    if action!='catalog_scope_stage':r['offer_sha256']='c'*64
    return r


def file(tmp_path, payload, *,mode=0o600):
    p=tmp_path/(payload.get('request_id','1'*32)+'.json')
    p.write_text(json.dumps(payload))
    p.chmod(mode)
    return p


@pytest.mark.parametrize('action',['catalog_scope_stage','catalog_scope_promote','catalog_scope_recover'])
def test_exact_three_root_actions_are_parsed_without_elevation(tmp_path,action):
    item=request(action)
    assert w._read_request(file(tmp_path,item))==item


@pytest.mark.parametrize('field,value',[
    ('schema_version','2.0'),('source_revision','0'),
    ('request_id','../bad'),('release_id','release-other'),
    ('admission_receipt_sha256','0'*64),('action','run_arbitrary_shell'),
    ('action','catalog_scope_unknown'),('offer_sha256','not-a-digest'),
])
def test_bad_root_action_binding_rejected(tmp_path,field,value):
    item=request('catalog_scope_promote')
    item[field]=value
    with pytest.raises(w.HostReconcileError):
        w._read_request(file(tmp_path,item))


def test_stage_rejects_extra_owner_or_recovery_fields(tmp_path):
    item=request()
    for name,value in (('offer_sha256','c'*64),('owner_approved',True),
                       ('signed_owner_proof',{'valid':False}),
                       ('docker_args',['--privileged'])):
        data=dict(item,**{name:value})
        with pytest.raises(w.HostReconcileError):
            w._read_request(file(tmp_path,data))


def test_permissive_request_file_is_rejected(tmp_path):
    item=request()
    with pytest.raises(w.HostReconcileError):
        w._read_request(file(tmp_path,item,mode=0o644))


def test_routing_to_trusted_root_module_before_normal_reconcile(tmp_path,monkeypatch):
    item=request()
    path=file(tmp_path,item)
    calls=[]
    monkeypatch.setattr(w,'_verify_main',lambda rev:calls.append(('verify_main',rev)))
    class Trusted:
        def execute_native_catalog_scoped_request(self,request):
            calls.append(('trusted_root',request['action']))
            return {'status':'catalog_offer_staged_without_mutation',
                    'release_id':request['release_id'],
                    'production_mutations':False}
    monkeypatch.setattr(w,'_trusted_catalog_scoped_promotion_module',lambda rev:Trusted())
    monkeypatch.setattr(w,'_write_result',lambda *args,**kw:calls.append(('result',kw['success'])))
    monkeypatch.setattr(w,'_mcp_revision',lambda:pytest.fail('catalog scoped request fell through to ordinary host reconciliation'))
    w._process(path)
    assert calls==[('verify_main',SHA),('trusted_root','catalog_scope_stage'),('result',True)]
    assert not path.exists()


def test_malformed_root_receipt_never_claims_success(tmp_path,monkeypatch):
    item=request();path=file(tmp_path,item)
    monkeypatch.setattr(w,'_verify_main',lambda rev:None)
    class Trusted:
        def execute_native_catalog_scoped_request(self,request):
            return {'status':'production_pair_verified','release_id':'release-unrelated'}
    monkeypatch.setattr(w,'_trusted_catalog_scoped_promotion_module',lambda rev:Trusted())
    receipts=[]
    monkeypatch.setattr(w,'_write_result',lambda *args,**kw:receipts.append(kw))
    w._process(path)
    assert receipts and receipts[0]['success'] is False
    assert not path.exists()
