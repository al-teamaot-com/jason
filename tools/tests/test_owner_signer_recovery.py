"""Synthetic fail-closed acceptance for the separately authorized signer recovery."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "owner_signer_recovery", ROOT / "tools/owner_signer_recovery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unprivileged_execution_fails_before_any_provider_or_docker_call(monkeypatch):
    m = load()
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(m, "docker", lambda *_: pytest.fail("Docker called"))
    with pytest.raises(m.RecoveryDenied, match="ROOT_NATIVE_EXECUTION_REQUIRED"):
        m.execute()


def test_policy_exact_one_action_without_standing_authority():
    m = load()
    policy = json.loads((ROOT / "config/owner-signer-recovery-2450-policy.json").read_text())
    assert policy["one_shot"] is True
    assert policy["operation"] == m.OPERATION
    assert policy["lkg_sha"] == m.LKG
    assert policy["mcp_image_sha256"] == m.MCP_IMAGE
    assert policy["runtime_image_sha256"] == m.RUNTIME_IMAGE
    assert policy["freeze_sha256"] == m.FREEZE_SHA
    assert policy["signer_public_sha256"] == m.PUBLIC_SHA
    assert policy["owner_authentication"] == "fresh_verified_entra_device_code"
    assert policy["native_deployer"] == str(m.DEPLOYER)
    assert str(m.LEDGER_DIR).startswith("/etc/jason-owner-release/")
    source = (ROOT / "tools/owner_signer_recovery.py").read_text()
    assert "get_access_token" not in source
    assert "owner_approved=True" not in source
    assert "ONE_SHOT" not in source or "one_shot" in source


def _fixtures(monkeypatch, tmp_path, m):
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"immutable freeze bytes\n")
    monkeypatch.setattr(m, "FREEZE", freeze)
    monkeypatch.setattr(m, "FREEZE_SHA", m.sha(freeze.read_bytes()))
    control = {
        "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {
            "complete": True, "revision": m.LKG,
            "runtime_revision": m.LKG, "mcp_revision": m.LKG,
            "host_revision": m.LKG,
            "runtime_image_id": m.RUNTIME_IMAGE, "mcp_image_id": m.MCP_IMAGE,
        }},
    }
    drift = {
        "status": "pass", "problems": [],
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    monkeypatch.setattr(
        m, "root_file", lambda path, **kw:
        json.dumps(control if path == m.CONTROL else drift).encode()
    )
    monkeypatch.setattr(m, "host_release",
                        lambda: Path("/opt/jason/releases") / m.LKG)
    runtime = {
        "Id": "runtime-unchanged", "Image": m.RUNTIME_IMAGE,
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
        "Config": {"Labels": {"com.teamaot.jason.source_revision": m.LKG}},
        "Mounts": [],
    }
    mcp = {
        "Id": "mcp-before", "Image": m.MCP_IMAGE,
        "State": {"Status": "running"},
        "Config": {
            "Labels": {"com.teamaot.jason.source_revision": m.LKG},
            "Env": ["JASON_OWNER_RELEASE_ED25519_KEY_PATH="],
        },
        "Mounts": [],
    }
    monkeypatch.setattr(m, "docker", lambda name: runtime if name == "jason-runtime" else mcp)
    return control, drift, runtime, mcp


def test_clean_live_baseline_passes_read_only_preflight(monkeypatch, tmp_path):
    m = load()
    _fixtures(monkeypatch, tmp_path, m)
    out = m.evidence(strict=True)
    assert out["mcp_container_id"] == "mcp-before"
    assert out["runtime_container_id"] == "runtime-unchanged"


@pytest.mark.parametrize("corruption", ["breaker", "stale", "new_mcp_image", "env"])
def test_preflight_refuses_untrusted_live_state(monkeypatch, tmp_path, corruption):
    m = load()
    control, drift, _, mcp = _fixtures(monkeypatch, tmp_path, m)
    if corruption == "breaker":
        control["circuit_breaker"]["state"] = "open"
    elif corruption == "stale":
        drift["observed_at"] = (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat()
    elif corruption == "new_mcp_image":
        mcp["Image"] = "sha256:" + "0" * 64
    else:
        mcp["Config"]["Env"] = ["JASON_OWNER_RELEASE_ED25519_KEY_PATH=/tmp/malicious"]
    with pytest.raises(m.RecoveryDenied):
        m.evidence(strict=True)


def test_device_code_approval_is_limited_and_never_persists_token(monkeypatch, capsys):
    m = load()
    calls = []
    def mock_form(url, params):
        calls.append(url)
        if url.endswith("/devicecode"):
            return {"user_code": "ABCD-1234",
                    "device_code": "one-use", "verification_uri": "https://login.microsoftonline.com/device",
                    "expires_in": 120, "interval": 5}
        return {"access_token": "synthetic-never-logged"}
    monkeypatch.setattr(m, "_form", mock_form)
    monkeypatch.setattr(m.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(m, "jwt_owner", lambda token: next(iter(sorted(m.OWNERS))))
    oid = m.interactive_owner()
    output = capsys.readouterr().out
    assert oid in m.OWNERS
    assert "synthetic-never-logged" not in output
    assert "EXACT_ACTION=" + m.OPERATION in output
    assert len(calls) == 2


def test_device_flow_provider_denial_is_fail_closed(monkeypatch):
    m = load()
    monkeypatch.setattr(m, "_form",
                        lambda *_: {"error": "unauthorized_client"})
    with pytest.raises(m.RecoveryDenied, match="ENTRA_DEVICE_FLOW_UNAVAILABLE"):
        m.interactive_owner()


@pytest.mark.parametrize("oid,tid,scope,valid", [
    ("bee80bdc-ffb0-4c50-b453-c09d4d411f5f", "f7054323-d52b-4863-8c2f-1898f0b6077c", "Jason.Read", True),
    ("11111111-1111-1111-1111-111111111111", "f7054323-d52b-4863-8c2f-1898f0b6077c", "Jason.Read", False),
    ("bee80bdc-ffb0-4c50-b453-c09d4d411f5f", "11111111-1111-1111-1111-111111111111", "Jason.Read", False),
    ("bee80bdc-ffb0-4c50-b453-c09d4d411f5f", "f7054323-d52b-4863-8c2f-1898f0b6077c", "Other.Read", False),
])
def test_owner_jwt_independently_checks_subject_tenant_and_scope(monkeypatch, oid, tid, scope, valid):
    m = load()
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(m, "PyJWKClient",
                        lambda *_: SimpleNamespace(
                            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
                        ))
    now = int(time.time())
    token = jwt.encode({
        "iss": "https://login.microsoftonline.com/" + m.TENANT + "/v2.0",
        "aud": m.CLIENT_ID, "tid": tid, "oid": oid, "scp": scope,
        "exp": now + 600, "iat": now, "nbf": now - 2,
    }, private, algorithm="RS256")
    if valid:
        assert m.jwt_owner(token) == oid
    else:
        with pytest.raises((m.RecoveryDenied, jwt.PyJWTError)):
            m.jwt_owner(token)


def test_root_record_is_one_shot_and_never_overwrites(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m.os, "fchown", lambda fd, uid, gid: None)
    target = tmp_path / "record.json"
    m.write_root_record(target, {"operation": m.OPERATION, "state": "claimed"})
    with pytest.raises(FileExistsError):
        m.write_root_record(target, {"operation": m.OPERATION, "state": "duplicate"})


def test_postcheck_rejects_writable_signer_bind(monkeypatch, tmp_path):
    m = load()
    _, _, runtime, old = _fixtures(monkeypatch, tmp_path, m)
    after = dict(old)
    after["Id"] = "changed"
    after["Config"] = dict(old["Config"])
    after["Config"]["Env"] = ["JASON_OWNER_RELEASE_ED25519_KEY_PATH=" + m.DEST]
    after["Mounts"] = [{
        "Type": "bind", "Source": str(m.PRIVATE),
        "Destination": m.DEST, "RW": True,
    }]
    monkeypatch.setattr(m, "docker", lambda name: runtime if name == "jason-runtime" else after)
    with pytest.raises(m.RecoveryDenied, match="READONLY_SIGNER_BIND_NOT_VERIFIED"):
        m.postcheck({"mcp_container_id": old["Id"], "runtime_container_id": runtime["Id"]})



def test_root_installed_source_digest_matches_exact_policy():
    m = load()
    policy = json.loads((ROOT / "config/owner-signer-recovery-2450-policy.json").read_text())
    assert m.sha((ROOT / "tools/owner_signer_recovery.py").read_bytes()) == policy["script_sha256"]
    assert len(policy["native_deployer_sha256"]) == 64
    assert policy["native_deployer_sha256"] == "2687a73e07d63693a057c3aa89cea0abb41d02cf1dcafb22df5ce82792c81eee"


def test_root_trust_rejects_symlink_and_non_root_file(tmp_path):
    m = load()
    target = tmp_path / "not-root-owned.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(m.RecoveryDenied):
        m.root_file(link)
    with pytest.raises(m.RecoveryDenied):
        m.root_file(target)


def test_owner_jwt_rejects_wrong_audience(monkeypatch):
    m = load()
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(m, "PyJWKClient",
                        lambda *_: SimpleNamespace(
                            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
                        ))
    now = int(time.time())
    token = jwt.encode({
        "iss": "https://login.microsoftonline.com/" + m.TENANT + "/v2.0",
        "aud": "unauthorized-client", "tid": m.TENANT,
        "oid": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        "scp": "Jason.Read", "iat": now, "exp": now + 300, "nbf": now - 1,
    }, private, algorithm="RS256")
    with pytest.raises(jwt.PyJWTError):
        m.jwt_owner(token)
