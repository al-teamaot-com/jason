"""Only one reviewed test-only owner-canary delta may coexist with the sealed catalog image."""
import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import catalog_scoped_release_admission as a
ROOT=Path(__file__).resolve().parents[2]

def test_reviewed_test_revision_is_protected_and_not_runtime():
    assert a.OWNER_CANARY_TEST_PATH in a.EXACT_BLOBS
    assert 'implementation/' in a.OWNER_CANARY_TEST_PATH
    assert '/tests/' in a.OWNER_CANARY_TEST_PATH
    assert a.OWNER_CANARY_TEST_PATH not in (a.SERVER_PATH,)
    current=(ROOT/a.OWNER_CANARY_TEST_PATH).read_bytes()
    assert hashlib.sha256(current).hexdigest()==a.OWNER_CANARY_REVIEWED_SHA256

def test_approved_test_only_change_requires_exact_pin_and_ancestor(monkeypatch):
    old=b'older sealed catalog test'
    new=(ROOT/a.OWNER_CANARY_TEST_PATH).read_bytes()
    monkeypatch.setattr(a,'git',lambda repo,*args:new)
    monkeypatch.setattr(a.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
    a.verified_owner_canary_test_only(ROOT,original=old,protected=old,current=new,
                                      main_sha='a'*40)
    with pytest.raises(a.CatalogScopeDenied,match='CATALOG_SOURCE_BLOB_CHANGED'):
        a.verified_owner_canary_test_only(ROOT,original=old,protected=old,current=new+b'edit',main_sha='a'*40)
    with pytest.raises(a.CatalogScopeDenied,match='CATALOG_SOURCE_BLOB_CHANGED'):
        a.verified_owner_canary_test_only(ROOT,original=old,protected=b'changed protected feature',current=new,main_sha='a'*40)
    monkeypatch.setattr(a.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=1))
    with pytest.raises(a.CatalogScopeDenied,match='CATALOG_SOURCE_BLOB_CHANGED'):
        a.verified_owner_canary_test_only(ROOT,original=old,protected=old,current=new,main_sha='a'*40)

def test_reviewed_commit_blob_must_match(monkeypatch):
    old=b'older sealed catalog test'
    new=(ROOT/a.OWNER_CANARY_TEST_PATH).read_bytes()
    monkeypatch.setattr(a,'git',lambda repo,*args:b'forged reviewed Git blob')
    with pytest.raises(a.CatalogScopeDenied,match='CATALOG_SOURCE_BLOB_CHANGED'):
        a.verified_owner_canary_test_only(ROOT,original=old,protected=old,current=new,main_sha='a'*40)

def test_exact_unmodified_test_blob_does_not_need_exception(monkeypatch):
    monkeypatch.setattr(a,'git',lambda *args:pytest.fail('no pinned Git blob read for unchanged source'))
    a.verified_owner_canary_test_only(ROOT,original=b'sealed',protected=b'sealed',current=b'sealed',main_sha='a'*40)
