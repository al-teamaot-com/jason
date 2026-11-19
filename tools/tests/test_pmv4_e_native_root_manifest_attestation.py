"""Read-only root manifest attestation with real sealed source bytes."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import pytest

from tools import pmv4_e_native_root_manifest_attestation as attestor
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_root_trust_stage as trust


def staged(tmp_path):
    target = tmp_path / "sealed"
    root = trust.RootTrustStager(
        source=packet.ROOT,
        target=target,
        native_signed_started=lambda: True,
        native_host_locked=lambda: True,
        native_freeze_locked=lambda: True,
        native_marker_absent=lambda: True,
        native_replacements_inert=lambda: True,
        production=False,
    )
    hashes = {
        p: sha256((packet.ROOT / p).read_bytes()).hexdigest()
        for p in packet.REVIEWED_PATHS
    }
    root.stage(source_sha="b"*40, exact_hashes=hashes)
    release_dir = tmp_path / "release"
    release_dir.mkdir(mode=0o700)
    scope = contract.draft(candidate_sha="b"*40, rollback_sha="a"*40)
    for name, value in (("manifest.json", scope["manifest"]),
                        ("source-scope.json", scope["source_scope"])):
        (release_dir/name).write_bytes(packet.canonical(value))
        (release_dir/name).chmod(0o444)
    release_dir.chmod(0o555)
    return root, release_dir, scope, hashes


def test_real_staged_source_and_exact_manifest_readback(tmp_path):
    root, release, scope, hashes = staged(tmp_path)
    result = attestor.inspect(
        source_root=root.target, release_dir=release, production=False,
    )
    assert result["status"] == "root_source_attested_no_release_authority"
    assert result["candidate_sha"] == "b"*40
    assert result["rollback_sha"] == "a"*40
    assert result["manifest_sha256"] == scope["manifest_sha256"]
    assert result["file_count"] == len(packet.REVIEWED_PATHS)
    assert result["release_authorized"] is False
    assert result["owner_proof_issued"] is False
    assert result["root_preflight_complete"] is False
    assert result["production_mutations"] is False
    root.recover_inert_stage(hashes)


@pytest.mark.parametrize("tamper", [
    "extra_source", "source_bytes", "source_symlink",
    "extra_manifest", "manifest_action", "scope_hash",
    "provider_write", "standing_authority", "freeze_changed",
])
def test_exact_root_source_tampering_denied(tmp_path, tamper):
    root, release, data, hashes = staged(tmp_path)
    if tamper == "extra_source":
        root.target.chmod(0o700)
        (root.target/"unreviewed.txt").write_text("unreviewed")
        (root.target/"unreviewed.txt").chmod(0o444)
        root.target.chmod(0o555)
    elif tamper == "source_bytes":
        parent = root.target/"tools"
        target = parent/"pmv4_e_unit_admission.py"
        parent.chmod(0o700)
        target.chmod(0o600)
        target.write_text("override")
        target.chmod(0o444)
        parent.chmod(0o555)
    elif tamper == "source_symlink":
        root.target.chmod(0o700)
        (root.target/"unexpected").symlink_to("/tmp")
        root.target.chmod(0o555)
    elif tamper == "extra_manifest":
        release.chmod(0o700)
        (release/"extra").write_text("no")
        (release/"extra").chmod(0o444)
        release.chmod(0o555)
    else:
        name = "source-scope.json" if tamper == "scope_hash" else "manifest.json"
        path = release/name
        doc = json.loads(path.read_text())
        if tamper == "manifest_action":
            doc["action"] = "unreviewed"
        elif tamper == "scope_hash":
            doc["exact_replacement_files_sha256"] = {}
        elif tamper == "provider_write":
            doc["provider_scope"] = {"provider": "autotask"}
        elif tamper == "standing_authority":
            doc["standing_authority"] = True
        elif tamper == "freeze_changed":
            doc["freeze_sha256"] = "0"*64
        path.chmod(0o600)
        path.write_text(json.dumps(doc))
        path.chmod(0o444)
    with pytest.raises(attestor.StageERootAttestationDenied):
        attestor.inspect(
            source_root=root.target, release_dir=release, production=False,
        )


def test_root_mode_rejects_uninstalled_developer_code(tmp_path):
    with pytest.raises(attestor.StageERootAttestationDenied,
                       match="CANONICAL_PRIVILEGED_INSTALL_REQUIRED"):
        attestor.inspect(
            source_root=tmp_path, release_dir=tmp_path,
            production=True,
        )
