"""A1 cross-host lock must preserve the real protected-body failure."""
import errno
import os
import pytest

from tools.pmv4_host_release_guard import IndependentHostGuard, HostGateDenied


def guard_fixture(tmp_path):
    old=tmp_path/"legacy.lock"
    new=tmp_path/"pmv4.lock"
    old.touch();new.touch()
    old.chmod(0o664)
    new.chmod(0o600)
    return IndependentHostGuard(
        current=tmp_path,releases=tmp_path,ledger=tmp_path,
        old_lock=old,new_lock=new,
        control_path=tmp_path,drift_path=tmp_path,
        production=False,enforce_protected_control=False,
    )


def test_real_os_error_from_body_is_not_misreported_as_lock_unavailable(tmp_path):
    guard=guard_fixture(tmp_path)
    with pytest.raises(OSError,match="SHADOW_CONTAINER_MEMORY_EXHAUSTED") as exc:
        with guard.host_release_transaction():
            assert guard._held is True
            raise OSError(errno.ENOMEM,"SHADOW_CONTAINER_MEMORY_EXHAUSTED")
    assert exc.value.errno==errno.ENOMEM
    assert guard._held is False
    with guard.host_release_transaction():
        assert guard._held is True


def test_host_lock_open_oserror_is_still_named_host_gate(tmp_path,monkeypatch):
    guard=guard_fixture(tmp_path)
    def fail_open(_path):
        raise OSError(errno.EACCES,"original permission denied")
    monkeypatch.setattr(guard,"_open_lock",fail_open)
    with pytest.raises(HostGateDenied,
                       match="PMV4_HOST_TRANSACTION_UNAVAILABLE"):
        with guard.host_release_transaction():
            pass
    assert guard._held is False


def test_body_hostgate_denial_not_swallowed(tmp_path):
    guard=guard_fixture(tmp_path)
    with pytest.raises(HostGateDenied,match="EXACT_RELEASE_SCOPE_DRIFT"):
        with guard.host_release_transaction():
            raise HostGateDenied("EXACT_RELEASE_SCOPE_DRIFT")
    assert guard._held is False
