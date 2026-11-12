"""PMv4 trust is a separately governed host installation, never a PR side effect."""
from __future__ import annotations

from pathlib import Path
import os
import pytest

from tools import pmv4_host_install_contract as install


ROOT = Path(__file__).resolve().parents[1]


def test_preprod_bundle_reuses_exact_existing_security_sources():
    manifest = install.reviewed_code_manifest(ROOT)
    assert manifest["production_install_authorized"] is False
    assert len(manifest["files"]) == len(install.BUNDLE_FILES)
    assert not any("private" in f["path"] or "signer" in f["path"]
                   for f in manifest["files"])
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])


def test_stage_audited_code_without_creating_host_control_or_signer(tmp_path):
    staged = tmp_path / "pmv4-preprod-source"
    manifest = install.reviewed_code_manifest(ROOT)
    report = install.stage_lab_bundle(ROOT, staged)
    assert report["status"] == "lab_bundle_verified"
    assert report["bundle_sha256"] == manifest["bundle_sha256"]
    assert report["production_installed"] is False
    assert install.verify_lab_bundle(staged, manifest)["file_count"] == 7
    assert not (staged / "control/host-mutation.lock").exists()
    assert not any("signer.key" in str(x) for x in staged.rglob("*"))


def test_mutation_of_lab_code_is_detected(tmp_path):
    staged = tmp_path / "pmv4-preprod-source"
    install.stage_lab_bundle(ROOT, staged)
    manifest = install.reviewed_code_manifest(ROOT)
    file = staged / install.BUNDLE_FILES[1]
    file.chmod(0o600)
    file.write_bytes(b"untrusted")
    file.chmod(0o400)
    with pytest.raises(ValueError, match="CODE_HASH_DRIFT"):
        install.verify_lab_bundle(staged, manifest)


def test_untrusted_mode_and_symlink_refused(tmp_path):
    staged = tmp_path / "pmv4-preprod-source"
    install.stage_lab_bundle(ROOT, staged)
    manifest = install.reviewed_code_manifest(ROOT)
    file = staged / install.BUNDLE_FILES[0]
    file.chmod(0o644)
    with pytest.raises(ValueError, match="CODE_MODE_DRIFT"):
        install.verify_lab_bundle(staged, manifest)
    file.chmod(0o400)
    file.unlink()
    file.symlink_to(ROOT / install.BUNDLE_FILES[0])
    with pytest.raises(ValueError, match="SYMLINK_IN_BUNDLE"):
        install.verify_lab_bundle(staged, manifest)


@pytest.mark.parametrize("target", [
    Path("relative/stage"),
    Path("/var/lib/jason/pmv4-shadow/stage"),
    Path("/usr/local/lib/jason/pmv4-trusted/stage"),
    Path("/etc/jason/pmv4-shadow/stage"),
])
def test_source_worktree_cannot_stage_protected_host_targets(target):
    with pytest.raises(ValueError, match="PMV4_STAGE_"):
        install._nonproduction_stage_root(target)


def test_parent_symlink_outside_temp_is_denied(tmp_path):
    link = tmp_path / "elsewhere"
    link.symlink_to("/etc")
    with pytest.raises(ValueError, match="PMV4_STAGE_OUTSIDE_TEMP_DENIED"):
        install._nonproduction_stage_root(link / "fake")


def test_live_inspection_does_not_install_or_claim_approval():
    report = install.inspect_live()
    assert report["production_mutation"] is False
    assert report["production_install_authorized"] is False
    assert report["status"] == "inspection_only"
    assert "cross_release_lock_ready" in report
    assert "release_gate" in report


def test_empty_host_baseline_rollback_preserves_no_state(tmp_path):
    staged = tmp_path / "pmv4-preprod-release"
    manifest = install.reviewed_code_manifest(ROOT)
    install.stage_lab_bundle(ROOT, staged)
    result = install.rollback_lab_bundle(staged, manifest)
    assert result["status"] == "empty_baseline_restored"
    assert result["baseline_sha"] == "0" * 40
    assert result["production_mutation"] is False
    assert not staged.exists()


def test_rollback_denies_tampered_bundle_and_preserves_foreign_files(tmp_path):
    staged = tmp_path / "pmv4-preprod-release"
    manifest = install.reviewed_code_manifest(ROOT)
    install.stage_lab_bundle(ROOT, staged)
    foreign = staged / "unexpected"
    foreign.write_text("protected")
    with pytest.raises(ValueError, match="CODE_MODE_DRIFT|FILE_SCOPE_DRIFT"):
        install.rollback_lab_bundle(staged, manifest)
    assert foreign.read_text() == "protected"
    assert staged.exists()
