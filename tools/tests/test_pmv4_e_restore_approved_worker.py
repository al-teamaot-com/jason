import os
from pathlib import Path

import pytest

from tools import pmv4_e_restore_approved_worker as repair


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip("requires disposable UID0 filesystem")
    state = tmp_path / "approved-install"
    state.mkdir(mode=0o700)
    before = b"approved old worker"
    after = b"approved Stage E worker"
    worker = tmp_path / "worker.py"
    worker.write_bytes(after)
    worker.chmod(0o755)
    backup = state / "worker-before.py"
    backup.write_bytes(before)
    backup.chmod(0o755)
    monkeypatch.setattr(repair, "STATE", state)
    monkeypatch.setattr(repair, "WORKER", worker)
    monkeypatch.setattr(repair, "BEFORE", repair.digest(before))
    monkeypatch.setattr(repair, "INSTALLED", repair.digest(after))
    return before, after


def test_restore_is_exact_idempotent_and_keeps_before_image(isolated):
    before, _ = isolated
    assert repair.restore().endswith("APPROVED_BEFORE_IMAGE_RESTORED")
    assert repair.WORKER.read_bytes() == before
    assert (repair.STATE / "worker-before.py").read_bytes() == before
    assert repair.restore().endswith("ALREADY_RESTORED")


def test_restore_denies_changed_worker(isolated):
    repair.WORKER.write_bytes(b"unapproved worker")
    with pytest.raises(PermissionError, match="CURRENT_DIGEST_CHANGED"):
        repair.restore()
    assert repair.WORKER.read_bytes() == b"unapproved worker"


def test_failed_atomic_replace_preserves_installed_worker(isolated, monkeypatch):
    _, after = isolated

    def failed(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(repair.os, "replace", failed)
    with pytest.raises(OSError):
        repair.restore()
    assert repair.WORKER.read_bytes() == after


def test_restore_never_changes_catalog_policy_or_breaker():
    source = Path(repair.__file__).read_text()
    assert "os.replace(pending, WORKER)" in source
    assert "CATALOG.write" not in source
    assert "production-control-state.json" not in source
