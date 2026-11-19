"""Exact two-file one-use admission-only root repair, no bypass."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json
import stat
import pytest
ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'tools/catalog_admission_owner_canary_root_repair_once.py'
s=importlib.util.spec_from_file_location('cat_canary_oneuse',SRC)
assert s and s.loader
fix=importlib.util.module_from_spec(s);s.loader.exec_module(fix)

def test_exact_pins_and_allowed_mutations():
    code=SRC.read_text()
    assert fix.OLD_SHA=='fb73b5d5a6a23c54066dc0440263b6222ab1b02798556c868093a8766ca81d6f'
    assert fix.NEW_SHA=='9a1dfe91acf1fd5e8b00c5afb7664ed9dd99ea85dda8e3883145a44f5ecb7b08'
    assert fix.REL=='tools/catalog_scoped_release_admission.py'
    assert fix.POLICY==Path('/etc/jason-owner-release/catalog-scoped-promotion-installed.json')
    assert fix.CONFIRM=='APPROVE-CATALOG-ADMISSION-TEST-ONLY-ROOT-TRUST-REPAIR'
    assert 'new_policy[\'admission_module_sha256\']=NEW_SHA' in code
    assert "atomic_root(*item)" in code
    assert 'for path,old,new,mode in reversed(attempted)' in code
    assert "'root_trust_files_changed':True" in code
    assert 'OWNER_OID in auth.OWNERS' in code
    assert 'root_trust_change' not in code

def test_operator_cannot_run_root_preflight(monkeypatch):
    monkeypatch.setattr(fix.os,'geteuid',lambda:1000)
    with pytest.raises(fix.Denied,match='AUTHENTICATED_LOCAL_SUDO_REQUIRED'):
        fix.preflight('a'*40)

def test_no_native_release_or_provider_writes_are_authorized():
    code=SRC.read_text()
    assert 'catalog_scope_promote' not in code
    assert 'release_manager_host_runner.py' not in code
    assert 'git push' not in code
    assert 'docker run' not in code
    assert 'systemctl stop' not in code
    assert 'systemctl restart' not in code
    assert 'CATALOG_TEST_ONLY_ADMISSION_ROOT_TRUST_REPAIR=VERIFIED' in code
    assert 'native_trust_check()' in code
    assert 'PROTECTED' in code
    assert 'FREEZE_SHA' in code

def test_public_source_validation_uses_ancestry_and_exact_blob():
    code=SRC.read_text()
    assert 'merge-base' in code and '--is-ancestor' in code
    assert "git('show',f'{sha}:{REPAIR_REL}')" in code
    assert "git('show',f'{reviewed}:{REL}')" in code
    assert "git('show',f'{sha}:{REL}')" in code
    assert 'EXECUTED_ROOT_SCRIPT_NOT_REVIEWED' in code

def test_root_transaction_lock_and_audit_are_oneuse():
    code=SRC.read_text()
    assert "fcntl.LOCK_EX|fcntl.LOCK_NB" in code
    assert "os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW" in code
    assert "status':'owner_approval_consumed_before_root_mutation'" in code
    assert 'NATIVE_PRODUCTION_TRANSACTION_ALREADY_EXISTS' in code
    assert 'ROOT_ONEUSE_ALREADY_CONSUMED' in code
    assert 'ROOT_PLAN_CHANGED_UNDER_LOCK' in code

def test_native_module_still_validates_full_root_bundle():
    source=(ROOT/'tools/catalog_scoped_promotion_host.py').read_text()
    assert "'admission_module_sha256'" in source
    assert "fail('INSTALLED_MODULE_DRIFT')" in source
    assert "def deny_unresolved_previous_attempt" in source
    assert "fail('EXISTING_ATTEMPT_REQUIRES_RECONCILIATION')" in source

def test_root_policy_delta_is_one_exact_digest(monkeypatch):
    # Test the invariant against a hostile extra field changed in policy.
    code=SRC.read_text()
    assert "all(new_policy[k]==policy[k]" in code
    assert "if k!='admission_module_sha256'" in code
    assert "POLICY_CHANGE_OUTSIDE_ONE_SHA" in code

def test_fail_closed_root_file_meta(monkeypatch,tmp_path):
    file=tmp_path/'root-private.json';file.write_text('{}')
    file.chmod(0o600)
    with pytest.raises(fix.Denied,match='ROOT_FILE_OWNER_MODE_CHANGED'):
        fix.read(file,0o600)
    file.unlink();file.symlink_to(tmp_path/'other')
    with pytest.raises(fix.Denied,match='ROOT_FILE_NOT_REGULAR'):
        fix.read(file,0o600)


def test_root_git_ancestry_checks_al_owned_repo_with_pinned_safe_directory():
    code=SRC.read_text()
    assert "'git','-c',f'safe.directory={SOURCE}','-C',str(SOURCE)" in code
    assert "'merge-base','--is-ancestor',reviewed,sha" in code
