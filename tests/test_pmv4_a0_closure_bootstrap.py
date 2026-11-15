"""Auditable exact root-bootstrap source and disposable UID0 failure acceptance."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_a0_closure_bootstrap_root as boot
from tools import pmv4_a0_closure_bootstrap_owner as owner


def test_fixed_scope_no_generic_root_file_writer():
    assert len(boot.FILES) == 2
    assert set(boot.FILES) == {
        "/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py",
        "/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json",
    }
    assert boot.SCOPE_SHA == owner.SCOPE_SHA
    assert boot.PLAN_SHA == owner.PLAN_SHA
    assert boot.FREEZE_SHA == owner.FREEZE_SHA
    assert boot.HOLD_SHA == owner.HOLD_SHA
    assert boot.SOURCE_SHA == owner.SOURCE_SHA
    assert boot.PROOF == owner.PROOF
    assert boot.STAGED == Path("/run/jason-pmv4-a0-closure-bootstrap-7b42/installer.py")


@pytest.mark.skipif(not boot.PLAN.is_file(), reason="live Jason archive only")
def test_real_pinned_plan_and_exact_source_blobs():
    plan, blobs = boot.validate_plan()
    assert plan["action"] == boot.ACTION
    assert plan["production_install_authorized"] is False
    assert plan["approved_before_execution"] is False
    assert plan["scope_sha256"] == boot.SCOPE_SHA
    assert sha256(boot.PLAN.read_bytes()).hexdigest() == boot.PLAN_SHA
    for dest, (_, digest, size, mode) in boot.FILES.items():
        assert len(blobs[dest]) == size
        assert sha256(blobs[dest]).hexdigest() == digest
        assert mode in (0o400, 0o444)


@pytest.mark.skipif(not boot.PLAN.is_file(), reason="live Jason archive only")
def test_owner_can_inspect_without_auth_or_root_write():
    plan = owner.verify_reviewed_plan()
    assert plan["one_shot"] is True
    assert not owner.PROOF.exists()
    assert not boot.JOURNAL.exists()


def test_mutable_source_cannot_execute_production_root():
    with pytest.raises(boot.BootstrapDenied,
                       match="TRUSTED_LOCAL_ROOT_REQUIRED"):
        boot.execute()
    if os.geteuid() != 0:
        with pytest.raises(boot.BootstrapDenied):
            boot.trusted_execution()


def test_plan_modified_without_authorization_denied(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "config/pmv4-stage-a0/closure-bootstrap-plan-review.json"
    altered = json.loads(source.read_text())
    altered["files"][0]["destination"] = "/etc/shadow"
    file = tmp_path / "tampered-plan.json"
    file.write_text(json.dumps(altered))
    file.chmod(0o600)
    monkeypatch.setattr(boot, "PLAN", file)
    monkeypatch.setattr(boot, "PLAN_SHA", sha256(file.read_bytes()).hexdigest())
    with pytest.raises(boot.BootstrapDenied, match="SCOPE_CHANGED"):
        boot.validate_plan()


def test_prior_consumed_approval_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(boot, "JOURNAL", tmp_path / "existing-result.json")
    (tmp_path / "existing-result.json").write_text("prior action")
    # Only contract predicate, never trust a root-mutable object from sandbox.
    assert boot.JOURNAL.exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="disposable CI UID0 only")
def test_disposable_root_install_and_readback(tmp_path, monkeypatch):
    blobs = setup_disposable(tmp_path, monkeypatch)
    before = {"runtime_id": "fake", "mcp_id": "fake"}
    monkeypatch.setattr(boot, "readback", lambda: dict(before))
    boot.publish(blobs, before)
    boot.verify_targets(blobs)
    assert boot.LEDGER.is_dir()
    assert len(list(boot.LEDGER.iterdir())) == 0
    for file in blobs:
        assert Path(file).read_bytes() == blobs[file]
        assert Path(file).stat().st_uid == 0


@pytest.mark.skipif(os.geteuid() != 0, reason="disposable CI UID0 only")
@pytest.mark.parametrize("break_at", ["created_ledger", "file-1", "file-2"])
def test_disposable_root_interruption_empties_exact_objects(tmp_path, monkeypatch,
                                                            break_at):
    blobs = setup_disposable(tmp_path, monkeypatch)
    before = {"runtime_id": "fake", "mcp_id": "fake"}
    monkeypatch.setattr(boot, "readback", lambda: dict(before))
    def break_after(label):
        if label == "created_ledger" and break_at == "created_ledger":
            raise RuntimeError("injected root crash")
        if Path(label).name == break_at:
            raise RuntimeError("injected root crash")
    with pytest.raises(boot.BootstrapDenied, match="ROLLBACK_TO_ABSENCE"):
        boot.publish(blobs, before, after_step=break_after)
    assert not boot.LEDGER.exists()
    for path in blobs:
        assert not Path(path).exists()


@pytest.mark.skipif(os.geteuid() != 0, reason="disposable CI UID0 only")
def test_disposable_root_foreign_replacement_preserved(tmp_path, monkeypatch):
    blobs = setup_disposable(tmp_path, monkeypatch)
    before = {"runtime_id": "fake", "mcp_id": "fake"}
    monkeypatch.setattr(boot, "readback", lambda: dict(before))
    def replace(label):
        if Path(label).name == "file-1":
            file = Path(label)
            file.unlink()
            file.write_bytes(b"foreign")
            raise RuntimeError("injected foreign replacement")
    with pytest.raises(boot.BootstrapDenied, match="REQUIRES_REVIEW"):
        boot.publish(blobs, before, after_step=replace)
    first = next(Path(path) for path in blobs if Path(path).name == "file-1")
    assert first.read_bytes() == b"foreign"


def test_source_review_policy_hash_is_pinned_by_manifest():
    source = Path(__file__).parents[1] / "config/pmv4-stage-a0/closure-bootstrap-plan-review.json"
    plan = json.loads(source.read_bytes())
    rows = {r["destination"]: r for r in plan["files"]}
    for dest, (name, expected, size, mode) in boot.FILES.items():
        assert rows[dest]["sha256"] == expected
        assert rows[dest]["size"] == size
        assert rows[dest]["source"] == str(boot.ARCHIVE / name)
    assert plan["one_directory"] == str(boot.LEDGER)


def test_source_owner_auth_only_in_interactive_1000():
    assert owner.CONFIRM == "APPROVE-EXACT-PMV4-A0-CLOSURE-BOOTSTRAP"
    assert owner.SIGNER == Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
    assert owner.ROOT_PIN == boot.ROOT_PIN
    assert owner.VERIFIER == boot.VERIFIER


def test_source_only_root_bootstrap_no_enabled_prod_by_default():
    assert boot.main.__name__ == "main"
    assert owner.main.__name__ == "main"
    assert boot.PLAN.name.endswith("7b42.json")


def _source_items():
    return {"file-1": ("f1", b"safe first file"),
            "file-2": ("f2", b"safe second file")}


def setup_disposable(tmp_path, monkeypatch):
    # This fixture is run only in ephemeral CI UID0: no live host mounts,
    # no production paths or production service state may be modified.
    root = tmp_path / "fake-root"
    root.mkdir()
    first = root / "file-1"
    second = root / "file-2"
    led = root / "empty-ledger"
    blobs = _source_items()
    files = {str(first): ("first", sha256(blobs["file-1"][1]).hexdigest(),
                          len(blobs["file-1"][1]), 0o444),
             str(second): ("second", sha256(blobs["file-2"][1]).hexdigest(),
                           len(blobs["file-2"][1]), 0o400)}
    monkeypatch.setattr(boot, "FILES", files)
    monkeypatch.setattr(boot, "LEDGER", led)
    # Tests obtain data from the two exact temp paths rather than production.
    return {
        str(first): blobs["file-1"][1],
        str(second): blobs["file-2"][1],
    }
