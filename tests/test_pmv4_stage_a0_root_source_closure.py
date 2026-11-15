"""Source-only regression for the exact Stage A0 one-file source repair."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_stage_a0_root_source_closure as repair
from tools import pmv4_stage_a0_sparse_source as sparse
from tools import pmv4_stage_a0_sparse_root_stage as rootstage

LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"


@pytest.fixture
def git_blobs():
    return sparse.git_object(Path(__file__).parents[1])


@pytest.fixture
def repair_policy():
    return {
        "candidate_sha": repair.CANDIDATE, "lkg_sha": LKG,
        "freeze_sha256": FREEZE, "file_path": repair.RELATIVE,
        "file_sha256": repair.MISSING_SHA256,
        "original_scope_sha256": repair.ORIGINAL_SCOPE,
        "proposal_sha256": repair.PROPOSAL_SHA256,
    }


def test_install_is_closed_from_source_checkout():
    assert repair.ROOT_SCRIPT == Path("/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py")
    assert repair.ZERO_WRITE_AUTHORITY_FROM_SOURCE is True
    with pytest.raises(repair.SourceClosureDenied, match="TRUSTED_ROOT_INSTALL_REQUIRED"):
        repair.execute()
    assert repair.main.__name__ == "main"


def test_exact_original_thirteen_and_added_fourteen(git_blobs, repair_policy, monkeypatch):
    monkeypatch.setattr(sparse, "REQUIRED", tuple(x for x in sparse.REQUIRED if x != repair.RELATIVE))
    source = SimpleNamespace(git_object=lambda _repo: git_blobs,
                             source_manifest=sparse.source_manifest)
    stage = SimpleNamespace(REPO=Path(__file__).parents[1])
    prior, after, payload = repair.exact_source_scopes(source, stage, repair_policy)
    assert prior["scope_sha256"] == repair.ORIGINAL_SCOPE
    assert len(prior["files"]) == 13
    assert len(after["files"]) == 14
    assert after["files"][-1] == {
        "path": repair.RELATIVE, "size": 9571,
        "sha256": repair.MISSING_SHA256, "mode": "0444", "uid": 0, "gid": 0,
    }
    assert sha256(payload).hexdigest() == repair.MISSING_SHA256


def test_prior_scope_rejects_injected_fourteenth(git_blobs, repair_policy):
    old_source = SimpleNamespace(git_object=lambda _repo: git_blobs,
                                 source_manifest=lambda *args, **kwargs: {
                                     "scope_sha256": repair.ORIGINAL_SCOPE,
                                     "files": [{"path": repair.RELATIVE}] * 13,
                                 })
    with pytest.raises(repair.SourceClosureDenied, match="PRIOR_SOURCE_SCOPE_DRIFT"):
        repair.exact_source_scopes(old_source, SimpleNamespace(REPO=Path("/tmp")), repair_policy)


def test_requires_missing_file_and_exclusive_immutable_write(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    repair._write_one_exact(dest, payload, test_only=True)
    assert dest.read_bytes() == payload
    assert dest.stat().st_mode & 0o777 == 0o444
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload, test_only=True)
    dest.unlink()
    dest.symlink_to(tmp_path / "missing")
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload, test_only=True)


def test_partial_failure_rolls_back_only_created_file(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    with pytest.raises(RuntimeError, match="injected"):
        repair._write_one_exact(
            dest, payload, test_only=True,
            after_write=lambda: (_ for _ in ()).throw(RuntimeError("injected")),
        )
    assert not dest.exists()
    assert dest.parent.is_dir()


def test_cannot_replace_foreign_file_during_rollback(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    foreign = b"foreign content"
    def replace_with_foreign():
        dest.unlink()
        dest.write_bytes(foreign)
        raise RuntimeError("foreign")
    with pytest.raises(RuntimeError, match="foreign"):
        repair._write_one_exact(dest, payload, test_only=True, after_write=replace_with_foreign)
    assert dest.read_bytes() == foreign


def test_rejects_wrong_digest_and_non_temp_sandbox(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload + b"tampered", test_only=True)
    with pytest.raises(repair.SourceClosureDenied, match="PRODUCTION_ROOT_REQUIRED"):
        repair._write_one_exact(dest, payload, test_only=False)


def test_scope_binds_only_one_file(repair_policy):
    scope = repair.repair_scope(repair_policy)
    assert len(scope) == 64
    assert repair.repair_scope({**repair_policy, "proposal_sha256": "0" * 64}) != scope
    assert repair.repair_scope({**repair_policy, "file_sha256": "0" * 64}) != scope


def test_trusted_policy_rejects_scope_broadening(monkeypatch):
    from types import SimpleNamespace
    script = b"fixed rooted code"
    base = {
        "schema_version": "1.0", "action": repair.ACTION, "one_shot": True,
        "candidate_sha": repair.CANDIDATE, "lkg_sha": LKG,
        "file_path": repair.RELATIVE, "file_sha256": repair.MISSING_SHA256,
        "original_scope_sha256": repair.ORIGINAL_SCOPE,
        "proposal_sha256": repair.PROPOSAL_SHA256,
        "freeze_sha256": FREEZE, "promotion_hold_sha256": "a" * 64,
        "mcp_image_sha256": "sha256:" + "b" * 64,
        "runtime_image_sha256": "sha256:" + "c" * 64,
        "script_sha256": sha256(script).hexdigest(),
        "owner_authentication": "fresh-entra-oauth-signed-exact-action",
        "install_scope": "only-one-missing-root-owned-stage-a0-source",
        "no_services_changed": True, "no_provider_writes": True,
    }
    import json
    stored = {"policy": base}
    stage = SimpleNamespace(secure_root_read=lambda path, **kwargs:
                            json.dumps(stored["policy"]).encode()
                            if path == repair.POLICY else script)
    assert repair.trusted_policy(stage) == base
    for key, value in (("one_shot", False), ("file_path", "tools/arbitrary.py"),
                       ("action", "other"), ("no_provider_writes", False),
                       ("candidate_sha", "d" * 40),
                       ("script_sha256", "e" * 64)):
        stored["policy"] = {**base, key: value}
        with pytest.raises(repair.SourceClosureDenied):
            repair.trusted_policy(stage)


def test_prior_root_rejects_existing_target(tmp_path):
    root = tmp_path / "root"
    target = root / repair.RELATIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"foreign")
    stage = SimpleNamespace(verify_staged_source=lambda *args: None)
    with pytest.raises(repair.SourceClosureDenied, match="NOT_ABSENT"):
        repair.verify_prior(stage, root, {"files": []})
    target.unlink()
    target.symlink_to(tmp_path / "absent")
    with pytest.raises(repair.SourceClosureDenied, match="NOT_ABSENT"):
        repair.verify_prior(stage, root, {"files": []})


def test_no_arbitrary_target_even_in_disposable_sandbox(tmp_path, git_blobs):
    parent = tmp_path / "release" / "other"
    parent.mkdir(parents=True)
    parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(parent / Path(repair.RELATIVE).name,
                                payload, test_only=True)


def test_review_policy_binds_live_readback_and_helper_hash():
    import json
    root = Path(__file__).parents[1]
    policy = json.loads((root / "config/pmv4-stage-a0/root-source-closure-policy-review.json").read_text())
    helper = (root / "tools/pmv4_stage_a0_root_source_closure.py").read_bytes()
    assert set(policy) == repair.REQUIRED_POLICY
    assert policy["script_sha256"] == sha256(helper).hexdigest()
    assert policy["action"] == repair.ACTION
    assert policy["candidate_sha"] == repair.CANDIDATE
    assert policy["file_sha256"] == repair.MISSING_SHA256
    assert policy["one_shot"] is True
    assert policy["no_services_changed"] is True
    assert policy["no_provider_writes"] is True
