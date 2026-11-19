"""Operator cannot check root-private journal; root alone enforces one-use."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import stat
import pytest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'tools/catalog_owner_renewal_operator_v3.py'
spec=importlib.util.spec_from_file_location('catalog_owner_operator_v3',SCRIPT)
assert spec is not None and spec.loader is not None
v3=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)

class FakeRootPrivate:
    def __init__(self,uid=0,mode=0o700,symlink=False,available=True):
        self.uid=uid;self.mode=mode;self.symlink=symlink;self.available=available
    def is_symlink(self): return self.symlink
    def lstat(self):
        if not self.available:raise PermissionError('no root parent access')
        return SimpleNamespace(st_uid=self.uid,st_mode=stat.S_IFDIR|self.mode,st_nlink=2)
    def __truediv__(self,name):
        pytest.fail('operator MUST NOT descend into root-private journal')
    def exists(self):
        pytest.fail('operator MUST NOT infer private transaction existence')

def test_operator_accepts_only_attested_root_owned_0700_parent(monkeypatch):
    monkeypatch.setattr(v3,'ROOT_NATIVE_TX_PARENT',FakeRootPrivate())
    assert v3.root_existing_attempt(None) is None

@pytest.mark.parametrize('root,reason',[
    (FakeRootPrivate(uid=1000),'BOUNDARY_UNTRUSTED'),
    (FakeRootPrivate(mode=0o755),'BOUNDARY_UNTRUSTED'),
    (FakeRootPrivate(mode=0o777),'BOUNDARY_UNTRUSTED'),
    (FakeRootPrivate(symlink=True),'SYMLINK'),
    (FakeRootPrivate(available=False),'UNAVAILABLE'),
])
def test_untrusted_parent_denied(monkeypatch,root,reason):
    monkeypatch.setattr(v3,'ROOT_NATIVE_TX_PARENT',root)
    with pytest.raises(PermissionError,match='EXACT_CATALOG_RENEWAL_DENIED_NATIVE_TRANSACTION_ROOT_'+reason):
        v3.root_existing_attempt(None)

def test_root_keeps_exact_one_use_and_duplicate_check():
    host=(ROOT/'tools/catalog_scoped_promotion_host.py').read_text()
    router=(ROOT/'tools/catalog_scoped_promotion_root.py').read_text()
    assert 'def deny_unresolved_previous_attempt(' in host
    assert "fail('EXISTING_ATTEMPT_REQUIRES_RECONCILIATION')" in host
    assert "fail('ANOTHER_SCOPED_RELEASE_ALREADY_ACTIVE')" in host
    assert "fail('RELEASE_ATTEMPT_ALREADY_EXISTS')" in host
    assert 'with host.transaction_lock(offer):' in router
    assert "fail('OFFER_RESTAGE_EXISTING_APPROVAL_OR_TRANSACTION')" in router

def test_signed_owner_proof_is_never_reused_and_no_public_transaction_forgery():
    code=SCRIPT.read_text()
    assert 'signed_predecessor(m)' in code
    assert 'm.promote_request(offer,new)' in code
    assert 'installed_catalog_recovery()' in code
    assert 'root_existing_attempt(m)' in code
    assert 'OWNER_TERMINAL_REQUIRED' in code
    assert 'EXACT_CATALOG_RELEASE=' in code
    assert 'state_root=m.STATE' in code
    assert '.exists():denied("EXISTING_NATIVE_TRANSACTION_NEEDS_RECONCILIATION")' not in code
    assert '/var/lib/jason-catalog-scoped-promotion/transactions' not in code

def test_no_provider_write_approval_or_root_module_replacement():
    code=SCRIPT.read_text()
    assert 'AUTOTASK_PROVIDER_WRITES' not in code
    assert 'NEW_HOST_SHA="39b51dda22be70f2468493fc68574fd4085713506d5a270aee863cf8fb697e9d"' in code
    assert 'NEW_ROUTER_SHA="9d34a497012816cc8b4c1dbcbe5ee5c55a644a3bc0ceb188f2e5e3c908160e66"' in code
    assert 'EXPIRED_PREDECESSOR_SCOPE_INVALID' in code
    assert 'FROZEN="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"' in code
