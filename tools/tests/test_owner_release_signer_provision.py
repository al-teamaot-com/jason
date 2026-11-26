"""Root-controlled non-Teams Owner signing key source contract."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/provision_owner_release_signer.py"


def load():
    spec = importlib.util.spec_from_file_location("owner_signer_provision", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signer_self_test_runs_without_sudo():
    result = subprocess.run([sys.executable, str(SCRIPT), "--self-test"],
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OWNER_SIGNER_SELF_TEST=PASS"


def test_symmetric_fingerprint_and_no_standing_authority(tmp_path):
    module = load()
    private_dir, trust_dir = tmp_path / "secret", tmp_path / "trust"
    first, digest = module.provision(private_dir, trust_dir, os.getuid(), os.getgid(), False)
    again, digest2 = module.provision(private_dir, trust_dir, os.getuid(), os.getgid(), False)
    assert (first, again) == ("PROVISIONED", "ALREADY_PROVISIONED")
    assert digest == digest2
    secret = private_dir / module.PRIVATE_NAME
    assert stat.S_IMODE(secret.stat().st_mode) == 0o400
    assert len(secret.read_bytes()) == 32
    p = json.loads((trust_dir / module.PUBLIC_NAME).read_text())
    assert p["public_key_sha256"] == digest
    assert p["standing_authority"] is False
    assert p["authorized_owner_subjects"] == module.SUBJECTS


def test_tampered_root_public_policy_rejected(tmp_path):
    module = load()
    private_dir, trust_dir = tmp_path / "secret", tmp_path / "trust"
    module.provision(private_dir, trust_dir, os.getuid(), os.getgid(), False)
    policy = trust_dir / module.PUBLIC_NAME
    data = json.loads(policy.read_text())
    data["standing_authority"] = True
    policy.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="ROOT_TRUST_MISMATCH"):
        module.provision(private_dir, trust_dir, os.getuid(), os.getgid(), False)


def test_partial_secret_provision_rejected(tmp_path):
    module = load()
    private_dir, trust_dir = tmp_path / "secret", tmp_path / "trust"
    private_dir.mkdir(mode=0o700)
    trust_dir.mkdir(mode=0o700)
    (private_dir / module.PRIVATE_NAME).write_bytes(b"x" * 32)
    with pytest.raises(PermissionError, match="INCOMPLETE_PREVIOUS_PROVISION"):
        module.provision(private_dir, trust_dir, os.getuid(), os.getgid(), False)


def test_symlink_private_directory_rejected(tmp_path):
    module = load()
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "private-link"
    symlink.symlink_to(target)
    with pytest.raises(PermissionError, match="DIRECTORY_SYMLINK"):
        module.provision(symlink, tmp_path / "trust", os.getuid(), os.getgid(), False)


def test_canonical_provision_paths_match_native_mcp_mount():
    module = load()
    assert str(module.PRIVATE_DIR / module.PRIVATE_NAME) == (
        "/var/lib/jason/runtime-secrets/owner-release/private_key")
    assert str(module.TRUST_DIR / module.PUBLIC_NAME) == (
        "/etc/jason-owner-release/verified-owner-public-key.json")


def test_allowlisted_owner_binding_matches_kernel():
    module = load()
    from kernel.signed_owner_release import EXACT_OWNER_OAUTH_SUBJECTS, TID
    assert module.TENANT == TID
    assert module.SUBJECTS == [
        {"owner_oid": oid, "owner_principal": principal}
        for oid, principal in sorted(EXACT_OWNER_OAUTH_SUBJECTS.items())
    ]


def test_dedicated_root_trust_never_changes_etc_jason_directory_mode():
    content = SCRIPT.read_text()
    assert 'TRUST_DIR = Path("/etc/jason-owner-release")' in content
    assert 'os.chmod(trust_dir.parent' not in content
    assert 'existing_etc_directory_unchanged' in content
