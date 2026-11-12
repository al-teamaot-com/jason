"""Stage A0 native-root transaction journal and crash/rollback acceptance.

All tests run only under a private /tmp mapping. No production path, signer,
provider, systemd unit or protected state is created or modified.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    TID, OWNER_OID, OWNER_PRINCIPAL, canonical, issue_exact_owner_release,
)
from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a_admission as admission
from tools import pmv4_stage_a_native_install as native

REPO = Path(__file__).resolve().parents[1]
SHA = "d" * 40
NOW = datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)
ID = "owner-mcp-" + "a" * 32


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(packet, "verify_exact_repository_head", lambda *_: None)
    sandbox = tmp_path / "host"
    sandbox.mkdir(mode=0o700)
    # Simulate only PRE-EXISTING parent directories. The installer may
    # create none of them and must never recursively replace them.
    for parent in ("usr/local/lib/jason", "var/lib/jason", "etc/jason"):
        (sandbox / parent).mkdir(parents=True)
    old = tmp_path / "shared-legacy.lock"
    old.touch(mode=0o600)
    old.chmod(0o600)
    scope = packet.build_scope(REPO, SHA)
    freeze = tmp_path / "frozen"
    freeze.write_bytes(b"tested-root-freeze")
    freeze_sha = sha256(freeze.read_bytes()).hexdigest()
    manifest = admission.exact_stage_a_manifest(scope, freeze_sha)
    key = Ed25519PrivateKey.generate()
    proof = issue_exact_owner_release(
        approval_id=ID, release_id="release-" + SHA[:16],
        candidate_sha=SHA, rollback_sha=packet.EMPTY_BASELINE,
        scope_sha256=scope["scope_sha256"],
        manifest_sha256=sha256(canonical(manifest)).hexdigest(),
        freeze_sha256=freeze_sha,
        verified_tenant_id=TID, verified_owner_oid=OWNER_OID,
        verified_principal=OWNER_PRINCIPAL,
        verified_organization_id="aot",
        confirmed_decision="approve", at=NOW,
        private_key=key,
    )
    health = {
        "preflight_evidence_satisfied": True,
        "stage_a_empty_baseline_verified": True,
        "root_only_target_parent_verification_needed": False,
        "breaker_state": "closed",
        "installation_ready": False,
        "production_install_authorized": False,
        "freeze_sha256": freeze_sha,
    }
    def installer():
        return native.NativeStageAInstaller(
            production=False, sandbox=sandbox, old_lock=old,
            owner_metadata=False, root_health=lambda: health.copy(),
            at=NOW + timedelta(seconds=30),
        )
    kwargs = dict(
        repo=REPO, candidate_sha=SHA, scope=scope, manifest=manifest,
        signed_proof=proof, freeze_path=freeze,
        ci_check=lambda sha: sha == SHA,
        approval_public_key=key.public_key(),
    )
    return sandbox, scope, freeze, health, kwargs, installer


def test_native_install_and_full_empty_baseline_recovery(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    root = installer()
    installed = root.install(**kwargs)
    assert installed["status"] == "installed"
    assert installed["owner_approval_id"] == ID
    assert installed["scope_sha256"] == scope["scope_sha256"]
    journal = root._journal(SHA)
    assert journal.is_file() and len(root._events(journal)) >= 27
    root._verify_objects(scope, partial=False)
    with pytest.raises(native.StageANativeDenied, match="EXISTING_JOURNAL"):
        installer().install(**kwargs)
    result = installer().recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))
    assert result["rollback_sha"] == packet.EMPTY_BASELINE
    assert result["status"] == "empty_baseline_restored"
    assert not any(root._map(p).exists()
                   for p in (packet.HOST_CODE, packet.ROOT, packet.ETC))
    assert journal.exists()
    assert root._events(journal)[-1]["event"] == "rolled_back"
    with pytest.raises(native.StageANativeDenied, match="RECOVERY_RECEIPT_INVALID"):
        installer().recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))


@pytest.mark.parametrize("step", [
    "dir:" + packet.HOST_CODE,
    "dir:" + packet.ROOT,
    "file:" + packet.ROOT + "/control/host-mutation.lock",
    "file:" + packet.ETC + "/entra-audience.json",
    "link:" + packet.CURRENT,
])
def test_crash_after_durable_step_recovers_no_foreign_objects(rig, step):
    sandbox, scope, freeze, health, kwargs, installer = rig
    def fault(at):
        if at == step:
            raise InterruptedError("simulated power loss after durable journal step")
    with pytest.raises(InterruptedError):
        installer().install(**kwargs, after_step=fault)
    result = installer().recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))
    assert result["status"] == "empty_baseline_restored"
    assert not any((sandbox / p.lstrip("/")).exists() for p in (
        packet.HOST_CODE, packet.ROOT, packet.ETC))
    assert installer()._journal(SHA).is_file()


@pytest.mark.parametrize("tamper", ["new_file", "bad_mode", "file_changed",
                                    "untrusted_link", "foreign_dir"])
def test_crashed_transaction_with_drift_fails_closed_before_deletion(rig, tamper):
    sandbox, scope, freeze, health, kwargs, installer = rig
    def fault(step):
        if step == "file:" + packet.ROOT + "/control/host-mutation.lock":
            raise InterruptedError("crash")
    with pytest.raises(InterruptedError):
        installer().install(**kwargs, after_step=fault)
    root = installer()
    target = root._map(packet.ROOT + "/control/host-mutation.lock")
    if tamper == "new_file":
        (target.parent / "foreign.data").write_bytes(b"unexpected")
    elif tamper == "foreign_dir":
        (target.parent / "unknown").mkdir()
    elif tamper == "bad_mode":
        target.chmod(0o644)
    elif tamper == "file_changed":
        target.chmod(0o600)
        target.write_bytes(b"untrusted")
    elif tamper == "untrusted_link":
        (target.parent / "extraneous").symlink_to("/etc")
    with pytest.raises(native.StageANativeDenied):
        root.recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))
    assert target.exists()


def test_journal_chain_tamper_or_truncation_blocks_recovery(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    root = installer()
    root.install(**kwargs)
    journal = root._journal(SHA)
    before = journal.read_bytes()
    journal.write_bytes(before[:-1])
    with pytest.raises(native.StageANativeDenied, match="JOURNAL_TRUNCATED"):
        installer().recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))
    journal.write_bytes(before)
    lines = before.splitlines()
    first = json.loads(lines[0])
    first["scope_sha256"] = "f" * 64
    lines[0] = json.dumps(first).encode()
    journal.write_bytes(b"\n".join(lines)+b"\n")
    with pytest.raises(native.StageANativeDenied, match="JOURNAL_CHAIN_INVALID"):
        installer().recover_empty(scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(native._canonical(kwargs["signed_proof"])))


def test_absent_owner_approval_or_wrong_scope_never_enters_journal(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    trial = kwargs.copy()
    trial["signed_proof"] = {}
    with pytest.raises(PermissionError):
        installer().install(**trial)
    assert list(sandbox.glob("*.jsonl")) == []
    trial = kwargs.copy()
    trial["ci_check"] = lambda sha: False
    with pytest.raises(PermissionError):
        installer().install(**trial)
    assert list(sandbox.glob("*.jsonl")) == []


def test_existing_legitimate_lock_contention_fails_closed(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    old = installer().old_lock
    fd = os.open(old, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(native.StageANativeDenied, match="SHARED_RELEASE_LOCK_BUSY"):
            installer().install(**kwargs)
        assert list(sandbox.glob("*.jsonl")) == []
    finally:
        os.close(fd)


def test_production_path_or_clock_overrides_never_reach_mutation(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    with pytest.raises(native.StageANativeDenied, match="PRODUCTION_ROOT_BOUNDARY"):
        native.NativeStageAInstaller(
            production=True, sandbox=sandbox, old_lock=installer().old_lock,
            owner_metadata=True, root_health=lambda: health)
    with pytest.raises(native.StageANativeDenied):
        native.NativeStageAInstaller(production=False,
                                     sandbox=Path("/var/lib/jason"),
                                     old_lock=installer().old_lock)


@pytest.mark.skipif(os.geteuid() != 0,
                    reason="actual native root metadata only on disposable CI")
def test_native_journal_real_uid_gid_and_owned_rollback_on_ephemeral_root(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    root = native.NativeStageAInstaller(
        production=False, sandbox=sandbox,
        old_lock=installer().old_lock, owner_metadata=True,
        root_health=lambda: health.copy(),
        at=NOW + timedelta(seconds=30),
    )
    recorded = root.install(**kwargs)
    assert recorded["status"] == "installed"
    journal = root._journal(SHA)
    assert journal.lstat().st_uid == 0
    assert journal.stat().st_mode & 0o777 == 0o600
    for row in scope["directories"] + scope["files"]:
        node = root._map(row["path"]).lstat()
        assert (node.st_uid, node.st_gid) == (row["uid"], row["gid"])
    rolled = root.recover_empty(
        scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(
            native._canonical(kwargs["signed_proof"])),
    )
    assert rolled["status"] == "empty_baseline_restored"
    assert journal.is_file() and root._events(journal)[-1]["event"] == "rolled_back"


def test_last_step_freeze_drift_blocks_commit_and_preserves_journal(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    def change_after_link(marker):
        if marker == "link:" + packet.CURRENT:
            freeze.write_bytes(b"not-the-signed-freeze")
    with pytest.raises(native.StageANativeDenied,
                       match="FREEZE_CHANGED_DURING_INSTALL"):
        installer().install(**kwargs, after_step=change_after_link)
    journal = installer()._journal(SHA)
    assert journal.exists()
    assert installer()._events(journal)[-1]["event"] != "verified_installed"
    rollback = installer().recover_empty(
        scope=scope, confirmed_approval_id=ID,
        confirmed_proof_sha256=native._hash(
            native._canonical(kwargs["signed_proof"])),
    )
    assert rollback["status"] == "empty_baseline_restored"


def test_dangling_symlink_replacing_approved_file_blocks_any_rollback(rig):
    sandbox, scope, freeze, health, kwargs, installer = rig
    def fault(step):
        if step == "file:" + packet.ROOT + "/control/host-mutation.lock":
            raise InterruptedError("crash")
    with pytest.raises(InterruptedError):
        installer().install(**kwargs, after_step=fault)
    root = installer()
    approved = root._map(packet.ROOT + "/control/host-mutation.lock")
    other = root._map(packet.ROOT + "/control/shadow-release.lock")
    approved.unlink()
    approved.symlink_to("/never/a/real/target")
    with pytest.raises(native.StageANativeDenied, match="FILE_SYMLINK"):
        root.recover_empty(
            scope=scope, confirmed_approval_id=ID,
            confirmed_proof_sha256=native._hash(
                native._canonical(kwargs["signed_proof"])),
        )
    assert approved.is_symlink()
    assert root._map(packet.ROOT).is_dir()
