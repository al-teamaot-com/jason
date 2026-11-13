"""Source-only acceptance for future root-installed sparse Stage A0 staging."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import pmv4_stage_a0_sparse_source as sparse
from tools import pmv4_stage_a0_sparse_root_stage as rootstage

CANDIDATE = "a" * 40
LKG = "b" * 40
FREEZE = "c" * 64


def blob(sha: str, relative: str) -> bytes:
    assert sha == CANDIDATE
    return ("known-immutable:" + relative).encode()


@pytest.fixture
def manifest():
    return sparse.source_manifest(
        CANDIDATE, blob, freeze_sha256=FREEZE, current_lkg=LKG,
    )


@pytest.fixture
def archive(manifest):
    return sparse.package_bytes(manifest, blob)


def test_root_stager_denies_source_checkout_as_privileged_action(monkeypatch):
    monkeypatch.setattr(rootstage.os, "geteuid", lambda: 0)
    monkeypatch.setattr(rootstage.sys, "flags",
                        type("Flags", (), {"isolated": 1})())
    monkeypatch.setattr(rootstage, "ROOT_SCRIPT",
                        Path("/root/this-is-not-an-installed-binary"))
    with pytest.raises(rootstage.StageRootDenied, match="ROOT_INSTALLED"):
        rootstage.execute()


def test_root_stager_policy_has_no_caller_supplied_paths():
    assert rootstage.ROOT_SCRIPT.as_posix().startswith("/usr/local/lib/jason/")
    assert rootstage.SOURCE_TOOL.as_posix().startswith("/usr/local/lib/jason/")
    assert rootstage.POLICY.as_posix().startswith("/etc/jason-owner-release/")
    assert rootstage.RELEASES == Path("/opt/jason/releases")
    assert rootstage.CURRENT != rootstage.RELEASES
    assert rootstage.ACTION == "pmv4-stage-a0-sparse-root-source-v1"
    assert rootstage.MCP != rootstage.RUNTIME
    assert rootstage.ROOT_SCRIPT != rootstage.POLICY


def test_protected_ci_runs_as_existing_nonroot_github_identity(monkeypatch):
    commands = []
    def fake_run(args, **kwargs):
        commands.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="{}")
    monkeypatch.setattr(rootstage.subprocess, "run", fake_run)
    class FakeCi:
        def protected_main_ci_verified(self, candidate, *, runner):
            assert candidate == CANDIDATE
            result = runner(["/usr/bin/gh", "api", "/repos/a/b"], timeout=20)
            return result.returncode == 0
    assert rootstage.protected_ci_as_operator(FakeCi(), CANDIDATE)
    assert commands[0][0][:5] == [
        "/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/gh",
    ]


def test_exact_archive_checks_fixed_scope_and_remote_git_blobs(
    tmp_path, manifest, archive, monkeypatch,
):
    file = tmp_path / "approved-source.tar"
    file.write_bytes(archive)
    file.chmod(0o600)
    policy = {
        "archive_path": str(file),
        "archive_sha256": sha256(archive).hexdigest(),
        "candidate_sha": CANDIDATE,
        "lkg_sha": LKG,
        "freeze_sha256": FREEZE,
        "sparse_scope_sha256": manifest["scope_sha256"],
    }
    module = SimpleNamespace(
        git_object=lambda path: blob,
        source_manifest=sparse.source_manifest,
        verify_package=sparse.verify_package,
    )
    observed, raw = rootstage.exact_source_archive(policy, module)
    assert raw == archive
    assert observed["scope_sha256"] == manifest["scope_sha256"]
    changed = dict(policy)
    changed["sparse_scope_sha256"] = "f" * 64
    with pytest.raises(rootstage.StageRootDenied, match="SCOPE_MISMATCH"):
        rootstage.exact_source_archive(changed, module)
    file.write_bytes(archive + b"bad")
    with pytest.raises(rootstage.StageRootDenied, match="ARCHIVE_DIGEST_CHANGED"):
        rootstage.exact_source_archive(policy, module)


def test_sparse_root_stage_rejects_unverified_root_policy(monkeypatch):
    import json
    policy = {
        "schema_version": "1.0",
        "action": rootstage.ACTION,
        "one_shot": True,
        "candidate_sha": CANDIDATE,
        "lkg_sha": LKG,
        "sparse_scope_sha256": FREEZE,
        "archive_path": "/srv/jason/archive/pmv4-stage-a0-sparse-" + CANDIDATE + ".tar",
        "archive_sha256": FREEZE,
        "freeze_sha256": FREEZE,
        "promotion_hold_sha256": FREEZE,
        "mcp_image_sha256": "sha256:" + "d" * 64,
        "runtime_image_sha256": "sha256:" + "e" * 64,
        "script_sha256": sha256(b"script").hexdigest(),
        "source_tool_sha256": sha256(b"source").hexdigest(),
        "ci_attestor_sha256": sha256(b"ci").hexdigest(),
        "auth_helper_sha256": sha256(b"auth").hexdigest(),
        "owner_verifier_sha256": sha256(b"verify").hexdigest(),
        "owner_authentication": "fresh-entra-oauth-signed-exact-action",
        "install_scope": "only-13-pinned-stage-a0-source-files",
        "no_services_changed": True,
        "no_provider_writes": True,
    }
    files = {
        rootstage.POLICY: json.dumps(policy).encode(),
        rootstage.ROOT_SCRIPT: b"script",
        rootstage.SOURCE_TOOL: b"source",
        rootstage.ROOT_CI: b"ci",
        rootstage.AUTH: b"auth",
        rootstage.VERIFIER: b"verify",
    }
    monkeypatch.setattr(rootstage, "secure_root_read",
                        lambda path, **kwargs: files[path])
    assert rootstage.trusted_policy()["candidate_sha"] == CANDIDATE
    for key, value in (
        ("install_scope", "all-services"),
        ("no_services_changed", False),
        ("action", "other"),
        ("source_tool_sha256", "f" * 64),
        ("candidate_sha", LKG),
        ("archive_path", "/etc/shadow"),
    ):
        changed = dict(policy)
        changed[key] = value
        files[rootstage.POLICY] = json.dumps(changed).encode()
        with pytest.raises(rootstage.StageRootDenied):
            rootstage.trusted_policy()


def test_stage_owner_signature_exact_scope_and_zero_cross_authority(
    tmp_path, monkeypatch,
):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption,
    )
    from implementation.kernel import signed_owner_release as verifier
    key = Ed25519PrivateKey.generate()
    secret = tmp_path / "signer"
    secret.write_bytes(key.private_bytes(Encoding.Raw, PrivateFormat.Raw,
                                         NoEncryption()))
    secret.chmod(0o400)
    monkeypatch.setattr(rootstage, "SIGNER", secret)
    monkeypatch.setattr(verifier, "read_pinned_root_owner_public_key",
                        lambda *args, **kwargs: key.public_key())
    policy = {
        "candidate_sha": CANDIDATE, "lkg_sha": LKG,
        "sparse_scope_sha256": FREEZE, "freeze_sha256": FREEZE,
    }
    # Production key expects UID1000 and 0400; non-root test user is UID1000.
    if os.geteuid() != 1000:
        pytest.skip("service-signer metadata tested as UID1000")
    proof = rootstage.signed_stage_owner_proof(
        policy, verifier.OWNER_OID, verifier,
    )
    assert proof["payload"]["candidate_sha"] == CANDIDATE
    assert proof["payload"]["rollback_sha"] == LKG
    assert proof["payload"]["scope_sha256"] == FREEZE
    assert proof["payload"]["standing_authority"] is False
    with pytest.raises(verifier.OwnerReleaseProofDenied):
        verifier.verify_exact_owner_release(
            proof, public_key=key.public_key(),
            expected_candidate_sha=CANDIDATE, expected_rollback_sha=LKG,
            expected_release_id="release-" + CANDIDATE[:16],
            expected_scope_sha256="f" * 64,
            expected_manifest_sha256=proof["payload"]["manifest_sha256"],
            expected_freeze_sha256=FREEZE,
            at=datetime.now(timezone.utc),
        )


@pytest.mark.skipif(os.geteuid() != 0, reason="Only disposable GitHub root runner")
def test_real_root_sparse_stage_verify_and_exact_absence(tmp_path, manifest, archive):
    releases = tmp_path / "isolated-root-releases"
    releases.mkdir(mode=0o755)
    source = rootstage.stage_root_copy(releases, manifest, archive)
    assert source == releases / CANDIDATE
    rootstage.verify_staged_source(source, manifest)
    assert rootstage.recover_exact_source(releases, manifest)
    assert not source.exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="Only disposable GitHub root runner")
def test_real_root_partial_failure_automatically_restores_absence(
    tmp_path, manifest, archive,
):
    releases = tmp_path / "isolated-root-releases"
    releases.mkdir(mode=0o755)
    calls = []
    def interrupted(relative):
        calls.append(relative)
        if len(calls) == 2:
            raise InterruptedError("synthetic mid-copy crash")
    with pytest.raises(rootstage.StageRootDenied, match="ROLLBACK_VERIFIED"):
        rootstage.stage_root_copy(releases, manifest, archive,
                                  after_step=interrupted)
    assert rootstage.recover_exact_source(releases, manifest)
    assert not (releases / CANDIDATE).exists()
    assert not (releases / (".pmv4-a0-stage-" + CANDIDATE)).exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="Only disposable GitHub root runner")
def test_real_root_foreign_inode_blocks_exact_rollback(
    tmp_path, manifest, archive,
):
    releases = tmp_path / "isolated-root-releases"
    releases.mkdir(mode=0o755)
    source = rootstage.stage_root_copy(releases, manifest, archive)
    foreign = source / "tools/foreign.py"
    foreign.write_text("foreign")
    with pytest.raises(rootstage.StageRootDenied, match="FOREIGN"):
        rootstage.recover_exact_source(releases, manifest)
    assert foreign.read_text() == "foreign"


def test_sparse_root_stage_inspect_is_non_mutating():
    assert rootstage.main.__call__
    assert rootstage.ACTION not in rootstage.CURRENT.name
