"""Safety tests for approved local AOT Microsoft 365 group identity bootstrap.

All tests use temporary database paths and fake OpenBao; never touch live secrets.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from kernel.client_boundaries import SQLiteClientBoundaryStore
import tools.microsoft_group_admin_identity_bootstrap as mod


def _temporary_boundary_db(tmp_path, monkeypatch):
    p = tmp_path / "boundaries.sqlite3"
    store = SQLiteClientBoundaryStore(p)
    store.close()
    monkeypatch.setattr(mod, "DB", p)
    return p


def test_manifest_is_bound_to_two_exact_verified_aot_apps():
    item = mod._manifest()
    assert item["tenant_id"] == mod.TENANT
    assert item["client_id"] == mod.CLIENT
    assert set(mod.PROFILES) == {"read", "write"}
    assert mod.PROFILES["read"]["application_id"] != mod.PROFILES["write"]["application_id"]
    assert mod.PROFILES["read"]["thumbprint"] != mod.PROFILES["write"]["thumbprint"]


def test_manifest_rejects_changed_client_tenant_and_app_ids(monkeypatch, tmp_path):
    base = json.loads(mod.MANIFEST.read_text())
    for change in ("client", "tenant", "app"):
        data = json.loads(json.dumps(base))
        if change == "client":
            data["client_id"] = "unapproved-client"
        elif change == "tenant":
            data["tenant_id"] = "22222222-2222-4222-8222-222222222222"
        else:
            data["required_group_write"]["application_id"] = (
                "33333333-3333-4333-8333-333333333333")
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps(data))
        monkeypatch.setattr(mod, "MANIFEST", p)
        with pytest.raises(mod.BootstrapDenied, match="MANIFEST"):
            mod._manifest()


def test_persist_exact_scope_idempotent_and_provider_filtered(monkeypatch, tmp_path):
    p = _temporary_boundary_db(tmp_path, monkeypatch)
    mod._check_existing_rows()
    first = mod._persist_boundaries()
    assert set(first) == {"read", "write"}
    mod._check_existing_rows()
    again = mod._persist_boundaries()
    assert first == again
    con = sqlite3.connect(p)
    try:
        rows = con.execute(
            "SELECT client_id,provider,external_tenant_id,profile,"
            "application_id,service_principal_id,status FROM client_boundaries"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 2
    for row in rows:
        client, provider, tenant, profile, app, sp, status = row
        found = next(s for s in mod.PROFILES.values() if s["provider"] == provider)
        assert client == mod.CLIENT and tenant == mod.TENANT
        assert app == found["application_id"] and profile == found["profile"]
        assert sp == found["service_principal_id"] and status == "validated"


def test_existing_wrong_tenant_is_denied_without_modification(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from kernel.client_boundaries import (
        ClientBoundary, BoundaryStatus, SQLiteClientBoundaryRepository,
    )
    p = _temporary_boundary_db(tmp_path, monkeypatch)
    store = SQLiteClientBoundaryStore(p)
    try:
        repo = SQLiteClientBoundaryRepository(store)
        read = mod.PROFILES["read"]
        repo.add(ClientBoundary(
            id="alien", client_id=mod.CLIENT, provider=read["provider"],
            external_tenant_id="99999999-9999-4999-8999-999999999999",
            primary_domain=mod.DOMAIN, profile=read["profile"],
            application_id=read["application_id"], status=BoundaryStatus.VALIDATED,
            consent_transaction_id="unapproved",
            created_at=datetime.now(timezone.utc),
            consented_at=datetime.now(timezone.utc),
            validated_at=datetime.now(timezone.utc),
            service_principal_id=read["service_principal_id"],
        ))
    finally:
        store.close()
    with pytest.raises(mod.BootstrapDenied, match="EXISTING_GROUP_BOUNDARY"):
        mod._check_existing_rows()
    con = sqlite3.connect(p)
    assert con.execute("SELECT COUNT(*) FROM client_boundaries").fetchone()[0] == 1
    con.close()


def test_nonroot_apply_refuses_before_openbao_contact(monkeypatch, tmp_path, capsys):
    _temporary_boundary_db(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "source_sha", lambda: "safe-head")
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_stage_values", lambda _: {
        "private_key_pem": "TEST-ONLY",
        "certificate_pem": "TEST-ONLY",
        "certificate_thumbprint": "A" * 40,
        "generation": "test-only",
    })
    monkeypatch.setattr(mod.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(mod, "admin_login", lambda *a, **k: pytest.fail("OpenBao must not be contacted"))
    monkeypatch.setattr(sys, "argv", ["bootstrap.py", "--apply", "--source-sha", "safe-head"])
    with pytest.raises(mod.BootstrapDenied, match="REQUIRES_AUTHENTICATED"):
        mod.main()
    assert "EXCLUDES=CODE_DEPLOYMENT" in capsys.readouterr().out
    con = sqlite3.connect(mod.DB)
    assert con.execute("SELECT COUNT(*) FROM client_boundaries").fetchone()[0] == 0
    con.close()


def test_existing_secret_conflict_denied_before_any_write(monkeypatch, tmp_path):
    _temporary_boundary_db(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "source_sha", lambda: "safe-head")
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_stage_values", lambda role: {
        "private_key_pem": "fake-private-key-"+role,
        "certificate_pem": "fake-public-key-"+role,
        "certificate_thumbprint": mod.PROFILES[role]["thumbprint"],
        "generation": "test-only",
    })
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(mod, "RECEIPT", tmp_path / "receipt.json")
    monkeypatch.setattr(mod, "EVENT_LOG", tmp_path / "events.jsonl")
    monkeypatch.setattr(mod.getpass, "getpass", lambda _: "fake-test-password")
    monkeypatch.setattr(mod, "admin_login", lambda *a, **k: "fake-admin-token")
    monkeypatch.setattr(mod, "_existing_secret", lambda *a: {"private_key_pem": "DIFFERENT"})
    monkeypatch.setattr(mod, "_check_approle_preexisting", lambda *a: None)
    monkeypatch.setattr(mod, "revoke_admin_token", lambda *a: None)
    monkeypatch.setattr(mod, "configure_read_approle", lambda **k: pytest.fail("No AppRole writes on conflict"))
    monkeypatch.setattr(sys, "argv", ["bootstrap.py", "--apply", "--source-sha", "safe-head"])
    with pytest.raises(mod.BootstrapDenied, match="EXISTING_OPENBAO_CREDENTIAL_CONFLICT"):
        mod.main()
    assert not mod.RECEIPT.exists()


def test_successful_exact_scope_fake_credentials_persist_safely(monkeypatch, tmp_path):
    p = _temporary_boundary_db(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "source_sha", lambda: "safe-head")
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_stage_values", lambda role: {
        "private_key_pem": "fake-private-test-only-" + role,
        "certificate_pem": "fake-public-test-only-" + role,
        "certificate_thumbprint": mod.PROFILES[role]["thumbprint"],
        "generation": "test-only",
    })
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(mod, "RECEIPT", receipt)
    monkeypatch.setattr(mod, "EVENT_LOG", tmp_path / "events.jsonl")
    monkeypatch.setattr(mod.getpass, "getpass", lambda _: "fake-password")
    monkeypatch.setattr(mod, "admin_login", lambda *a: "fake-admin-token")
    monkeypatch.setattr(mod, "_existing_secret", lambda *a: None)
    monkeypatch.setattr(mod, "_check_approle_preexisting", lambda *a: None)
    calls = []
    monkeypatch.setattr(mod, "configure_read_approle", lambda **k: (
        calls.append(("approle",k["provider"])) or {"credentials_created": True}
    ))
    monkeypatch.setattr(mod, "write_provider_secret", lambda **k: (
        calls.append(("secret",k["provider"],k["values"]["certificate_thumbprint"]))
    ))
    monkeypatch.setattr(mod, "revoke_admin_token", lambda *a: calls.append(("revoke",)))
    monkeypatch.setattr(mod, "_approle_tokens", lambda *a: {"read": object(), "write": object()})
    class Preflight:
        def __init__(self, **kwargs): pass
        def inspect(self, **kwargs):
            return SimpleNamespace(
                read_identity_verified=True,
                write_identity_verified=True,
                group_read_verified=True,
                user_read_verified=True,
                live_mutation_permitted=False,
            )
    monkeypatch.setattr(mod, "MicrosoftGroupTenantPreflight", Preflight)
    monkeypatch.setattr(sys, "argv", ["bootstrap.py", "--apply", "--source-sha", "safe-head"])
    assert mod.main() == 0
    data = json.loads(receipt.read_text())
    assert set(data["boundary_ids"]) == {"read", "write"}
    assert data["production_deployment"] is False
    assert data["service_restart"] is False
    assert data["graph_mutation"] is False
    assert "fake-private" not in receipt.read_text()
    assert "fake-admin-token" not in receipt.read_text()
    assert ("revoke",) in calls
    assert [c[0] for c in calls] == ["approle", "secret", "approle", "secret", "revoke"]
    con = sqlite3.connect(p)
    assert con.execute("SELECT COUNT(*) FROM client_boundaries").fetchone()[0] == 2
    con.close()



def test_openbao_rejects_unexpected_existing_role(monkeypatch, tmp_path):
    spec = mod.PROFILES["read"]
    provider = mod.PROVIDERS["microsoft_graph_group_read"]
    monkeypatch.setitem(provider, "credential_dir", tmp_path / "nonexistent")
    def fake_api(address, api_path, *, method, token):
        if "sys/policies" in api_path:
            return {"data": {"policy": mod.provider_policy_text("microsoft_graph_group_read")}}
        return {"data": {
            "bind_secret_id": True, "token_no_default_policy": False,
            "token_policies": [provider["policy_name"]], "token_type": "service",
        }}
    monkeypatch.setattr(mod, "api_request", fake_api)
    with pytest.raises(mod.BootstrapDenied, match="ROLE_CONFLICT"):
        mod._check_approle_preexisting("http://fake", "test", "read")


def test_openbao_rejects_nonidentical_existing_policy(monkeypatch, tmp_path):
    provider = mod.PROVIDERS["microsoft_graph_group_read"]
    monkeypatch.setitem(provider, "credential_dir", tmp_path / "nonexistent")
    monkeypatch.setattr(mod, "api_request", lambda *a, **k: {
        "data": {"policy": 'path "secret/data/unrelated" { capabilities = ["sudo"] }'}
    })
    with pytest.raises(mod.BootstrapDenied, match="POLICY_CONFLICT"):
        mod._check_approle_preexisting("http://fake", "test", "read")



def test_production_revision_guard_does_not_ignore_changed_image(monkeypatch):
    class Result:
        def __init__(self, value):
            self.stdout = value
    results = [
        Result("sha256:fake-image|true\n"),
        Result("unapproved-release-sha\n"),
        Result("true\n"),
    ]
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: results.pop(0))
    with pytest.raises(mod.BootstrapDenied, match="PRODUCTION_RUNTIME_DRIFT"):
        mod._check_runtime_unchanged()


def test_runtime_access_requires_real_owner_local_sudo(monkeypatch):
    monkeypatch.setattr(mod.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_USER", "al")
    with pytest.raises(mod.BootstrapDenied, match="AUTHENTICATED_AL_SUDO"):
        mod.prepare_runtime_approle_access(
            apply=False, approval_scope=mod.RUNTIME_ACCESS_APPROVAL)


def test_runtime_access_wrong_exact_scope_fails_before_credential_change(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(mod, "_verify_bootstrap_receipt", lambda: None)
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_check_existing_rows", lambda: None)
    files = []
    for role in ("read", "write"):
        for name in ("role-id", "secret-id"):
            p = tmp_path / f"{role}-{name}"
            p.write_text("FAKE-TEST-CREDENTIAL-NOT-REAL")
            files.append((p, 0, 0o600))
    monkeypatch.setattr(mod, "_runtime_access_sources", lambda: files)
    monkeypatch.setattr(mod, "RUNTIME_ACCESS_RECEIPT", tmp_path / "receipt.json")
    monkeypatch.setattr(
        mod.os, "fchown", lambda *args: pytest.fail("Must not change modes"))
    monkeypatch.setattr(
        mod.os, "fchmod", lambda *args: pytest.fail("Must not change modes"))
    with pytest.raises(mod.BootstrapDenied, match="EXACT_OWNER_APPROVAL_REQUIRED"):
        mod.prepare_runtime_approle_access(
            apply=True, approval_scope="unrelated-unapproved-action")
    assert not (tmp_path / "receipt.json").exists()


def test_runtime_access_preflight_never_mutates_credentials(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(mod, "_verify_bootstrap_receipt", lambda: None)
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_check_existing_rows", lambda: None)
    monkeypatch.setattr(
        mod, "_runtime_access_sources", lambda: [
            (tmp_path / name, 0, 0o600)
            for name in ("read-role-id", "read-secret-id",
                         "write-role-id", "write-secret-id")])
    monkeypatch.setattr(mod, "RUNTIME_ACCESS_RECEIPT", tmp_path / "receipt.json")
    monkeypatch.setattr(
        mod.os, "fchown", lambda *args: pytest.fail("Preflight may not mutate"))
    monkeypatch.setattr(
        mod.os, "fchmod", lambda *args: pytest.fail("Preflight may not mutate"))
    mod.prepare_runtime_approle_access(apply=False, approval_scope="")
    assert "RUNTIME_ACCESS_PREFLIGHT=PASS; CHANGES=NONE" in capsys.readouterr().out


def test_runtime_access_four_file_exact_change_and_audit_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(mod, "_verify_bootstrap_receipt", lambda: None)
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_check_existing_rows", lambda: None)
    monkeypatch.setattr(mod, "source_sha", lambda: "f" * 40)
    files = []
    for role in ("read", "write"):
        for name in ("role-id", "secret-id"):
            p = tmp_path / f"{role}-{name}"
            p.write_text("FAKE-TEST-CREDENTIAL-NOT-REAL")
            files.append((p, 0, 0o600))
    monkeypatch.setattr(mod, "_runtime_access_sources", lambda: files)
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(mod, "RUNTIME_ACCESS_RECEIPT", receipt)
    # The test never elevates privileges: the four fake identities below model
    # root's descriptor-scoped chgrp/chmod, without touching actual mode/owner.
    real_fstat = mod.os.fstat
    overrides = {}
    def fake_fstat(fd):
        x = real_fstat(fd)
        # Preserve the complete os.stat_result ABI. Pytest and CPython may
        # consult st_size/st_ino on unrelated file descriptors during capture.
        import os
        fields=list(x)
        fields[0]=(x.st_mode & ~0o777) | overrides.get(fd, (0, 0o600))[1]
        fields[4]=0
        fields[5]=overrides.get(fd, (0, 0o600))[0]
        return os.stat_result(fields)
    monkeypatch.setattr(mod.os, "fstat", fake_fstat)
    def fake_chown(fd, uid, gid):
        assert uid == 0 and gid in {0,1000}
        overrides[fd] = (gid, overrides.get(fd, (0,0o600))[1])
    def fake_chmod(fd, mode):
        assert mode in {0o600,0o640}
        overrides[fd] = (overrides.get(fd, (0,0o600))[0], mode)
    monkeypatch.setattr(mod.os, "fchown", fake_chown)
    monkeypatch.setattr(mod.os, "fchmod", fake_chmod)
    mod.prepare_runtime_approle_access(
        apply=True, approval_scope=mod.RUNTIME_ACCESS_APPROVAL)
    info=json.loads(receipt.read_text())
    assert info["approved_scope"]==mod.RUNTIME_ACCESS_APPROVAL
    assert info["file_count"]==4
    assert info["production_deployment"] is False
    assert info["graph_mutation"] is False
    assert len([v for v in overrides.values() if v==(1000, 0o640)])==4


def test_runtime_access_failed_mode_change_restores_original_descriptor_metadata(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(mod.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(mod, "_verify_bootstrap_receipt", lambda: None)
    monkeypatch.setattr(mod, "_check_runtime_unchanged", lambda: None)
    monkeypatch.setattr(mod, "_check_existing_rows", lambda: None)
    paths=[]
    for role in ("read", "write"):
        for name in ("role-id", "secret-id"):
            p=tmp_path / f"{role}-{name}"
            p.write_text("FAKE-TEST-CREDENTIAL-NOT-REAL")
            paths.append((p,0,0o600))
    monkeypatch.setattr(mod, "_runtime_access_sources", lambda: paths)
    receipt=tmp_path / "receipt.json"
    monkeypatch.setattr(mod,"RUNTIME_ACCESS_RECEIPT",receipt)
    real_fstat=mod.os.fstat
    state={}
    def fake_fstat(fd):
        x=real_fstat(fd)
        gid,mode=state.get(fd,(0,0o600))
        import os
        fields=list(x)
        fields[0]=(x.st_mode & ~0o777)|mode
        fields[4]=0
        fields[5]=gid
        return os.stat_result(fields)
    monkeypatch.setattr(mod.os,"fstat",fake_fstat)
    def fchown(fd,uid,gid):
        state[fd]=(gid,state.get(fd,(0,0o600))[1])
    first_failure=[True]
    def fchmod(fd,mode):
        if mode==0o640 and first_failure[0]:
            first_failure[0]=False
            raise PermissionError("synthetic chmod failed")
        state[fd]=(state.get(fd,(0,0o600))[0],mode)
    monkeypatch.setattr(mod.os,"fchown",fchown)
    monkeypatch.setattr(mod.os,"fchmod",fchmod)
    with pytest.raises(PermissionError,match="synthetic chmod failed"):
        mod.prepare_runtime_approle_access(
            apply=True,approval_scope=mod.RUNTIME_ACCESS_APPROVAL)
    assert not receipt.exists()
    assert all(row == (0,0o600) for row in state.values())
