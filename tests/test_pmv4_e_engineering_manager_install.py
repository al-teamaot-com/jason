"""Exact native adapter file custody and rollback tests, without production."""
from hashlib import sha256
import os
from pathlib import Path
import pytest
from tools import pmv4_e_engineering_manager_install as m

ROOT=Path(__file__).resolve().parents[1]


def test_native_helpers_are_pinned_to_existing_reviewed_code():
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==pin for name,pin in m.NATIVE.items())
    assert len(m.UNITS)==4


def test_target_set_is_finite_and_never_includes_breaker_or_application():
    paths=m.target_set("a"*40)
    assert m.PAUSE in paths and m.POLICY in paths and m.ENV in paths
    assert all(m.USER_UNITS/name in paths and m.SYSTEM_UNITS/name in paths for name in m.UNITS)
    assert not any(p.name in ("production-control-state.json","production-drift.json",
                             "production-deployment-freeze","auto-promotion-incident-hold")
                   for p in paths)
    with pytest.raises(PermissionError):m.target_set("../../etc")


def test_recovery_images_exact_target_set():
    paths={Path("/one"),Path("/two")}
    original={Path("/one"):m.image(b"before",1000,0o600),Path("/two"):None}
    assert m.decode(m.encode(original),paths)==original
    data=m.encode(original);data["/foreign"]=None
    with pytest.raises(PermissionError,match="RECOVERY_TARGET_SET"):m.decode(data,paths)


@pytest.mark.skipif(os.getuid()!=1000 or os.getgid()!=1000,reason="fixture requires native non-root UID/GID")
def test_real_file_compare_and_swap_and_rollback(tmp_path):
    p=tmp_path/"target"
    old=m.image(b"before",1000,0o600);new=m.image(b"after",1000,0o600)
    p.write_bytes(old[0]);p.chmod(0o600)
    def no_replace(fd,source,target):
        assert m.snapshot_at(fd,target) is None
        os.rename(source,target,src_dir_fd=fd,dst_dir_fd=fd)
    m.replace_exact(p,old,new,no_replace)
    assert m.snapshot(p)==new
    with pytest.raises(PermissionError,match="BEFORE_IMAGE_CHANGED"):
        m.replace_exact(p,old,None,no_replace)
    m.replace_exact(p,new,old,no_replace)
    m.replace_exact(p,old,None,no_replace)
    m.replace_exact(p,None,old,no_replace)
    assert m.snapshot(p)==old


@pytest.mark.skipif(os.getuid()!=1000 or os.getgid()!=1000,reason="fixture requires native non-root UID/GID")
def test_recovery_never_deletes_foreign_staged_bytes(tmp_path):
    target=tmp_path/"target"; value=m.image(b"reviewed",1000,0o600)
    staged=tmp_path/(".engineering-manager-target-"+m.digest(value[0])[:24]+".tmp")
    staged.write_bytes(b"foreign");staged.chmod(0o600)
    with pytest.raises(PermissionError,match="FOREIGN_STAGED_TEMP"):
        m.cleanup_staged(target,(value,))
    assert staged.read_bytes()==b"foreign"
    staged.write_bytes(value[0])
    m.cleanup_staged(target,(value,))
    assert not staged.exists()


def test_root_adapter_retains_existing_authority_boundaries():
    source=(ROOT/"tools/pmv4_e_engineering_manager_install.py").read_text()
    assert 'adapter.actor = n["owner"](plan)' in source
    assert 'source_review(self.candidate, self.p) == self.code' in source
    assert 'self.n["locks"]()' in source
    assert 'request_root_control_transition' in source
    assert 'replace_exact(PAUSE,self.before[PAUSE],None' in source
    assert 'RESUME_SCOPE_NOT_AUTHORIZED' in source
    assert 'RECOVERY_ALREADY_TERMINAL' in source
    assert 'docker restart' not in source
    assert 'force_close_breaker' not in source
