"""Real root UID/GID/mode acceptance, confined to disposable GitHub /tmp.

Not run on Jason production. Never targets the actual /etc, /usr/local,
production LKG, signer, service, containers, or protected root state.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools import pmv4_stage_a_lab as lab
from tools import pmv4_stage_a_packet as packet

pytestmark = pytest.mark.skipif(
    os.geteuid() != 0, reason="root-metadata acceptance runs ONLY on disposable CI",
)
REPO = Path(__file__).resolve().parents[1]
SHA = "f" * 40


def _sandbox(tmp_path):
    assert str(tmp_path).startswith("/tmp/")
    return lab.sandbox_setup(tmp_path / "isolated-root-host")


def test_root_owned_bundle_group_isolation_and_initial_empty_rollback(tmp_path):
    sandbox = _sandbox(tmp_path)
    scope = packet.build_scope(REPO, SHA)
    assert scope["rollback_sha"] == "0" * 40
    assert scope["production_services_restart"] is False
    assert scope["provider_writes"] is False
    assert scope["owner_issuer_enabled"] is False
    installed = lab.stage(REPO, sandbox, scope, root_metadata=True)
    assert installed["root_metadata_checked"] is True
    assert installed["production_mutation"] is False
    assert lab.verify(REPO, sandbox, scope, root_metadata=True)["status"] == "verified"
    for item in scope["directories"]:
        observed = lab._mapped(sandbox, item["path"]).lstat()
        assert (observed.st_uid, observed.st_gid) == (item["uid"], item["gid"])
    for item in scope["files"]:
        observed = lab._mapped(sandbox, item["path"]).lstat()
        assert (observed.st_uid, observed.st_gid) == (item["uid"], item["gid"])
    restored = lab.rollback(REPO, sandbox, scope, root_metadata=True)
    assert restored["rollback_sha"] == "0" * 40
    assert restored["production_mutation"] is False


def test_root_mode_rejects_owner_drift_before_any_rollback_mutation(tmp_path):
    sandbox = _sandbox(tmp_path)
    scope = packet.build_scope(REPO, SHA)
    lab.stage(REPO, sandbox, scope, root_metadata=True)
    item = scope["files"][0]
    target = lab._mapped(sandbox, item["path"])
    before_sha = packet._digest(target.read_bytes())
    os.chown(target, 0, 2222)
    with pytest.raises(ValueError, match="STAGE_A_LAB_FILE_TAMPERED"):
        lab.rollback(REPO, sandbox, scope, root_metadata=True)
    assert target.exists() and packet._digest(target.read_bytes()) == before_sha
    os.chown(target, item["uid"], item["gid"])
    assert lab.rollback(REPO, sandbox, scope, root_metadata=True)["status"] == (
        "empty_baseline_restored"
    )


def test_root_mode_synthetic_midinstall_crash_and_verified_recovery(tmp_path):
    sandbox = _sandbox(tmp_path)
    scope = packet.build_scope(REPO, SHA)
    with pytest.raises(InterruptedError, match="SYNTHETIC_INTERRUPTION"):
        lab.stage(REPO, sandbox, scope, stop_after_files=3, root_metadata=True)
    assert lab.verify(
        REPO, sandbox, scope, allow_partial=True, root_metadata=True,
    )["status"] == "verified"
    result = lab.rollback(
        REPO, sandbox, scope, allow_partial=True, root_metadata=True,
    )
    assert result["status"] == "empty_baseline_restored"
    assert result["rollback_sha"] == "0" * 40
