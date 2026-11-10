"""Release signer bootstrap is root-controlled and excludes Teams prompts."""
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
DEPLOY = ROOT / "infrastructure/jason-mcp/production-deploy.sh"


def load():
    spec = importlib.util.spec_from_file_location("owner_provision", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_self_test_creates_no_live_secrets():
    result = subprocess.run([sys.executable, str(SCRIPT), "--self-test"],
                            capture_output=True, text=True, timeout=12)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OWNER_SIGNER_SELF_TEST=PASS"


def test_private_and_root_public_policy_exact(tmp_path):
    m = load()
    directory = tmp_path / "owner-release"
    result, fingerprint = m.provision(directory, os.getuid(), os.getgid(), False)
    assert result == "PROVISIONED"
    priv = directory / m.PRIVATE_NAME
    policy = json.loads((directory / m.PUBLIC_NAME).read_text())
    assert stat.S_IMODE(priv.stat().st_mode) == 0o400
    assert len(priv.read_bytes()) == 32
    assert policy["standing_authority"] is False
    assert policy["authorized_owner_subjects"] == m.OWNER_SUBJECTS
    assert policy["public_key_sha256"] == fingerprint
    again, same_fingerprint = m.provision(directory, os.getuid(), os.getgid(), False)
    assert again == "ALREADY_PROVISIONED"
    assert same_fingerprint == fingerprint


def test_tampered_policy_fails_closed(tmp_path):
    m = load()
    directory = tmp_path / "owner-release"
    m.provision(directory, os.getuid(), os.getgid(), False)
    pub = directory / m.PUBLIC_NAME
    policy = json.loads(pub.read_text())
    policy["standing_authority"] = True
    pub.write_text(json.dumps(policy))
    with pytest.raises(ValueError, match="TRUST_POLICY_MISMATCH"):
        m.provision(directory, os.getuid(), os.getgid(), False)


def test_incomplete_key_pair_fails_closed(tmp_path):
    m = load()
    directory = tmp_path / "owner-release"
    directory.mkdir(mode=0o700)
    (directory / m.PRIVATE_NAME).write_bytes(b"unsafe")
    with pytest.raises(PermissionError, match="INCOMPLETE_PRIOR_PROVISION"):
        m.provision(directory, os.getuid(), os.getgid(), False)


def test_symlink_directory_fails_closed(tmp_path):
    m = load()
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "link"
    linked.symlink_to(target)
    with pytest.raises(PermissionError, match="DIRECTORY_SYMLINK"):
        m.provision(linked, os.getuid(), os.getgid(), False)


def test_source_only_signer_bind_is_policy_scoped():
    s = DEPLOY.read_text()
    assert '[ "$OWNER_RELEASE_POLICY_VERSION" = "3.1" ]' in s
    assert '[ "$IMAGE" != "jason-mcp:rollback-current" ]' in s
    assert '"/etc/jason/owner-release/service-ed25519.private"' in s
    assert '"/run/jason-secrets/owner-release/service-ed25519.private"' in s
    assert '--set-env "JASON_OWNER_RELEASE_ED25519_KEY_PATH=$OWNER_RELEASE_SIGNER_CONTAINER"' in s
    assert '--add-readonly-bind "$OWNER_RELEASE_SIGNER_HOST:$OWNER_RELEASE_SIGNER_CONTAINER"' in s
    assert '"${OWNER_RELEASE_SIGNER_ARGS[@]}"' in s
