"""Isolated non-mutating tests for the one-transaction MCP AppRole projection."""
from __future__ import annotations
import importlib.util
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    path = ROOT / "tools" / "governed_provider_oauth_projection.py"
    spec = importlib.util.spec_from_file_location("cc_oauth_projection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(monkeypatch, tmp_path, m):
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"canonical freeze contents")
    monkeypatch.setattr(m, "FREEZE", freeze)
    monkeypatch.setattr(m, "FREEZE_SHA", m.sha(freeze.read_bytes()))
    control = {
        "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {
            "complete": True,
            "revision": m.LKG,
            "runtime_revision": m.LKG, "mcp_revision": m.LKG,
            "host_revision": m.LKG,
            "runtime_image_id": m.RUNTIME_IMAGE,
            "mcp_image_id": m.MCP_IMAGE,
        }},
    }
    drift = {"status": "pass", "problems": [],
             "observed_at": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(
        m, "root_file", lambda p, **kw:
        json.dumps(control if p == m.CONTROL else drift).encode(),
    )
    monkeypatch.setattr(
        m, "HOST_RELEASE",
        SimpleNamespace(resolve=lambda strict=False:
                        Path("/opt/jason/releases") / m.LKG),
    )
    monkeypatch.setattr(m, "credential_file", lambda path, owner: None)
    monkeypatch.setattr(
        m, "runtime_identity",
        lambda: SimpleNamespace(pw_uid=1000, pw_gid=1000),
    )
    rt = {
        "Id": "unchanged-runtime", "Image": m.RUNTIME_IMAGE,
        "State": {"Health": {"Status": "healthy"}, "Status": "running"},
        "Config": {"Labels": {"com.teamaot.jason.source_revision": m.LKG}},
        "Mounts": [],
    }
    mcp = {
        "Id": "original-mcp", "Image": m.MCP_IMAGE,
        "State": {"Status": "running"},
        "Config": {
            "Labels": {"com.teamaot.jason.source_revision": m.LKG},
            "Env": [
                "JASON_SOURCE_REVISION=" + m.LKG,
                "JASON_OWNER_RELEASE_ED25519_KEY_PATH=" + m.SIGNER_DEST,
                "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false",
            ],
            "User": "1000:1000",
        },
        "HostConfig": {"ReadonlyRootfs": True, "Privileged": False,
                       "CapDrop": ["ALL"]},
        "Mounts": [
            {"Type": "bind", "Source": m.SIGNER_HOST,
             "Destination": m.SIGNER_DEST, "RW": False},
        ],
        "NetworkSettings": {"Networks": {"jason-core": {}}},
    }
    values = {m.RUNTIME: rt, m.LIVE: mcp}
    monkeypatch.setattr(m, "docker", lambda name: values[name])
    return control, drift, values


def test_unprivileged_execution_is_denied_even_when_owner_requested(monkeypatch):
    m = load()
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        m, "docker",
        lambda name: pytest.fail("No docker access before root trust"),
    )
    with pytest.raises(m.ProjectionDenied, match="ROOT_ISOLATED_PYTHON_REQUIRED"):
        m.execute()


def test_exact_readonly_preflight_passes(monkeypatch, tmp_path):
    m = load()
    state(monkeypatch, tmp_path, m)
    before = m.clean_production()
    assert before["mcp_id"] == "original-mcp"
    assert before["runtime_id"] == "unchanged-runtime"
    assert before["mounts"] == [("bind", m.SIGNER_HOST, m.SIGNER_DEST, False)]


@pytest.mark.parametrize("kind", [
    "open_breaker", "stale_drift", "changed_freeze", "wrong_mcp_image",
    "wrong_runtime_image", "no_signer", "already_mounted",
    "pmv4_activated", "running_with_root",
])
def test_fail_closed_preflight(monkeypatch, tmp_path, kind):
    m = load()
    control, drift, objects = state(monkeypatch, tmp_path, m)
    if kind == "open_breaker":
        control["circuit_breaker"]["state"] = "open"
    elif kind == "stale_drift":
        drift["observed_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=220)
        ).isoformat()
    elif kind == "changed_freeze":
        m.FREEZE.write_bytes(b"not frozen")
    elif kind == "wrong_mcp_image":
        objects[m.LIVE]["Image"] = "sha256:" + "0" * 64
    elif kind == "wrong_runtime_image":
        objects[m.RUNTIME]["Image"] = "sha256:" + "0" * 64
    elif kind == "no_signer":
        objects[m.LIVE]["Mounts"].clear()
    elif kind == "already_mounted":
        objects[m.LIVE]["Mounts"].append(
            {"Type": "bind", "Source": m.ROLE_SOURCE,
             "Destination": m.ROLE_DEST, "RW": False},
        )
    elif kind == "pmv4_activated":
        objects[m.LIVE]["Config"]["Env"].append(
            "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true"
        )
    elif kind == "running_with_root":
        objects[m.LIVE]["HostConfig"]["Privileged"] = True
    with pytest.raises(m.ProjectionDenied):
        m.clean_production()


def test_exact_mount_postcheck(monkeypatch, tmp_path):
    m = load()
    _, _, objects = state(monkeypatch, tmp_path, m)
    pre = m.clean_production()
    fresh = dict(objects[m.LIVE])
    fresh["Id"] = "new-mcp-id"
    fresh["Mounts"] = list(objects[m.LIVE]["Mounts"]) + [
        {"Type": "bind", "Source": m.ROLE_SOURCE,
         "Destination": m.ROLE_DEST, "RW": False},
        {"Type": "bind", "Source": m.SECRET_SOURCE,
         "Destination": m.SECRET_DEST, "RW": False},
    ]
    fresh["Config"] = dict(objects[m.LIVE]["Config"])
    fresh["Config"]["Env"] = list(objects[m.LIVE]["Config"]["Env"]) + [
        "JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH=" + m.ROLE_DEST,
        "JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH=" + m.SECRET_DEST,
        "JASON_CONSTANT_CONTACT_OAUTH_DB=" + m.OAUTH_DB,
    ]
    objects[m.LIVE] = fresh
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    assert m.validate_post(pre)["verified"] is True


@pytest.mark.parametrize("change", [
    "writable_role", "third_mount", "new_runtime", "pmv4_enabled",
    "lost_owner_signer", "different_network", "privileged",
])
def test_postcheck_denies_unexpected_changes(monkeypatch, tmp_path, change):
    m = load()
    _, _, objects = state(monkeypatch, tmp_path, m)
    pre = m.clean_production()
    fresh = dict(objects[m.LIVE])
    fresh["Id"] = "new-mcp-id"
    fresh["Mounts"] = list(objects[m.LIVE]["Mounts"]) + [
        {"Type": "bind", "Source": m.ROLE_SOURCE,
         "Destination": m.ROLE_DEST, "RW": False},
        {"Type": "bind", "Source": m.SECRET_SOURCE,
         "Destination": m.SECRET_DEST, "RW": False},
    ]
    fresh["Config"] = dict(objects[m.LIVE]["Config"])
    fresh["Config"]["Env"] = list(objects[m.LIVE]["Config"]["Env"]) + [
        "JASON_CONSTANT_CONTACT_OPENBAO_ROLE_ID_PATH=" + m.ROLE_DEST,
        "JASON_CONSTANT_CONTACT_OPENBAO_SECRET_ID_PATH=" + m.SECRET_DEST,
        "JASON_CONSTANT_CONTACT_OAUTH_DB=" + m.OAUTH_DB,
    ]
    fresh["HostConfig"] = dict(objects[m.LIVE]["HostConfig"])
    fresh["NetworkSettings"] = dict(objects[m.LIVE]["NetworkSettings"])
    objects[m.LIVE] = fresh
    if change == "writable_role":
        fresh["Mounts"][1]["RW"] = True
    elif change == "third_mount":
        fresh["Mounts"].append({"Type": "bind", "Source": "/tmp",
                                "Destination": "/secret", "RW": False})
    elif change == "new_runtime":
        objects[m.RUNTIME]["Id"] = "modified-runtime"
    elif change == "pmv4_enabled":
        fresh["Config"]["Env"].append("JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true")
    elif change == "lost_owner_signer":
        fresh["Mounts"].pop(0)
    elif change == "different_network":
        fresh["NetworkSettings"] = {"Networks": {"other": {}}}
    elif change == "privileged":
        fresh["HostConfig"]["Privileged"] = True
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    with pytest.raises(m.ProjectionDenied):
        m.validate_post(pre)


def test_existing_owner_signed_jwt_helper_is_required():
    m = load()
    assert m.TRUSTED_AUTH == Path("/usr/local/lib/jason/owner_signer_recovery.py")
    assert m.DEPLOYER == Path("/usr/local/lib/jason/deploy_live_container_owner_signer_2450.py")
    assert m.ROLLBACK != m.LIVE
    assert m.ROLE_SOURCE.endswith("/constant-contact-oauth-client-approle/role-id")
    assert m.SECRET_SOURCE.endswith("/constant-contact-oauth-client-approle/secret-id")


def test_bad_device_code_refused_before_claim(monkeypatch):
    m = load()
    auth = SimpleNamespace(
        TENANT="test", CLIENT_ID="test-client", SCOPE="test-scope",
        _form=lambda *a, **kw: {"error": "invalid_client"},
    )
    with pytest.raises(m.ProjectionDenied, match="ENTRA_DEVICE_CHALLENGE_UNAVAILABLE"):
        m.fresh_owner_approval(auth)


def test_owner_device_code_completed_validates_signed_oid(monkeypatch, capsys):
    m = load()
    polls = []
    def request(url, fields):
        polls.append(url)
        if url.endswith("/devicecode"):
            return {
                "device_code": "one-use-synthetic",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://login.microsoft.com/device",
                "expires_in": 120, "interval": 5,
            }
        return {"access_token": "private-token-not-to-log"}
    auth = SimpleNamespace(
        TENANT="synthetic-tenant", CLIENT_ID="synthetic-client",
        SCOPE="synthetic-scope", _form=request,
        jwt_owner=lambda t: ("owner-verified" if t == "private-token-not-to-log"
                             else pytest.fail("invalid token")),
    )
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    assert m.fresh_owner_approval(auth) == "owner-verified"
    output = capsys.readouterr().out
    assert "private-token-not-to-log" not in output
    assert "EXACT_ACTION=" + m.OPERATION in output
    assert "READONLY_APPROLE_BINDS=2" in output


def test_atomic_root_one_shot_ledger_does_not_overwrite(monkeypatch, tmp_path):
    m = load()
    monkeypatch.setattr(m.os, "fchown", lambda fd, uid, gid: None)
    p = tmp_path / "claim.json"
    m.atomic_record(p, {"operation": m.OPERATION, "state": "claimed"})
    with pytest.raises(FileExistsError):
        m.atomic_record(p, {"operation": m.OPERATION, "state": "duplicate"})


def test_program_only_offers_check_and_execute():
    m = load()
    assert m.OPERATION == "constant-contact-oauth-mcp-approle-bind-v1"
    source = (ROOT / "tools" / "governed_provider_oauth_projection.py").read_text()
    assert "--set-env" in source
    assert "--add-readonly-bind" in source
    assert "OWNER_AUTH=verified_entra_oauth" in source
    assert "READ_PROFILE=" not in source
    assert "IMPORT_PROFILE=" not in source
    assert "JASON_CONSTANT_CONTACT_IMPORT_PROFILE=" not in source



def test_rollback_retention_budget_bounded(monkeypatch):
    m = load()
    monkeypatch.setattr(
        m.subprocess, "check_output",
        lambda *args, **kwargs: "\n".join(
            "jason-runtime-rollback-%02d" % i for i in range(19)
        ),
    )
    m.verify_rollback_budget()
    monkeypatch.setattr(
        m.subprocess, "check_output",
        lambda *args, **kwargs: "\n".join(
            "jason-runtime-rollback-%02d" % i for i in range(20)
        ),
    )
    with pytest.raises(m.ProjectionDenied, match="RETENTION_BUDGET_FULL"):
        m.verify_rollback_budget()


def test_production_transaction_lock_serializes_activation(monkeypatch, tmp_path):
    m = load()
    path = tmp_path / "transaction.lock"
    path.write_text("")
    monkeypatch.setattr(m, "TRANSACTION_LOCK", path)
    with m.production_gate():
        with pytest.raises(m.ProjectionDenied, match="ANOTHER_PRODUCTION_TRANSACTION_ACTIVE"):
            with m.production_gate():
                pass
    with m.production_gate():
        pass


def test_source_manifest_stays_callback_only():
    m = load()
    assert m.ROLLBACK.startswith("jason-mcp-rollback-")
    assert m.LIVE == "jason-mcp-pilot"
    assert m.RUNTIME == "jason-runtime"
    source = (ROOT / "tools" / "governed_provider_oauth_projection.py").read_text()
    assert "JASON_CONSTANT_CONTACT_READ_PROFILE=" not in source
    assert "JASON_CONSTANT_CONTACT_IMPORT_PROFILE=" not in source
    assert "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true" not in source
