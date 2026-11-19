"""SEC-007 offline tests for the bounded catalog root rebind action."""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SRC = Path(__file__).resolve().parents[1] / "catalog_root_worker_rebind_once.py"
spec = importlib.util.spec_from_file_location("catalog_root_worker_rebind_tested", SRC)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_readonly_plan_hash_and_exact_no_provider_scope(monkeypatch):
    original = {
        "schema_version": "1.0", "action": "catalog-root-worker-and-projection-rebind-v1",
        "status": "SOURCE_ONLY_REBIND_PREP_NOT_AUTHORIZED",
        "requires_fresh_signed_exact_owner": True,
        "provider_write_authorized": False, "runtime_mcp_promotion_authorized": False,
        "production_mutations": False,
    }
    original["plan_sha256"] = sha256(m.canonical(original)).hexdigest()
    monkeypatch.setattr(m, "file", lambda *a, **k: json.dumps(original).encode())
    assert m.read_plan()["plan_sha256"] == original["plan_sha256"]
    original["provider_write_authorized"] = True
    with pytest.raises(PermissionError, match="PLAN_HASH_MISMATCH"):
        m.read_plan()
    original["plan_sha256"] = sha256(m.canonical({k:v for k,v in original.items() if k != "plan_sha256"})).hexdigest()
    with pytest.raises(PermissionError, match="PLAN_SCOPE_INVALID"):
        m.read_plan()


def test_git_blob_raw_bytes_are_preserved(monkeypatch):
    seen = []
    def fake_run(argv, stdout, stderr, check, timeout):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"first line\nsecond line\n", b"")
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m.run_bytes("git", "show", "abc") == b"first line\nsecond line\n"
    assert m.run("git", "show", "abc") == "first line\nsecond line"
    assert seen == [["git", "show", "abc"], ["git", "show", "abc"]]


def test_protected_main_requires_latest_green_check(monkeypatch):
    main = "a" * 40
    required = ["repository-hygiene", "governed-security-regressions"]
    responses = {
        "repos/al-teamaot-com/jason/branches/main":
            {"name": "main", "protected": True, "commit": {"sha": main}},
        "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks":
            {"strict": True, "checks": [{"context": k, "app_id": 15368} for k in
                                        required + ["runtime-service","system-registry","documentation"]]},
        "repos/al-teamaot-com/jason/commits/" + main + "/check-runs?per_page=100":
            {"check_runs": [
                {"name": name, "head_sha": main, "status": "completed",
                 "conclusion": "success", "completed_at": "2026-11-17T21:00:00Z", "id": 9}
                for name in required + ["runtime-service","system-registry","documentation"]
            ] + [
                {"name": "repository-hygiene", "head_sha": main, "status": "completed",
                 "conclusion": "cancelled", "completed_at": "2026-11-17T20:00:00Z", "id": 2}
            ]},
    }
    monkeypatch.setattr(m, "run", lambda *args, **kwargs: json.dumps(responses[args[2]]))
    assert m.protected_main_ci(main)
    responses["repos/al-teamaot-com/jason/commits/" + main + "/check-runs?per_page=100"]["check_runs"][0]["conclusion"] = "failure"
    with pytest.raises(PermissionError, match="PROTECTED_CHECK_NOT_GREEN"):
        m.protected_main_ci(main)


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    folder = tmp_path / "catalog"
    tools = folder / "tools"
    tools.mkdir(parents=True)
    (folder / "config").mkdir()
    monkeypatch.setattr(m,"WORKER",tmp_path/"worker.py")
    monkeypatch.setattr(m,"ROOT_POLICY",tmp_path/"policy.json")
    monkeypatch.setattr(m,"PROJECTION",tools/"pmv4_mcp_projection.py")
    monkeypatch.setattr(m,"FREEZE",tmp_path/"freeze")
    monkeypatch.setattr(m,"LEDGER",tmp_path/"ledger")
    original_worker=b"old-worker\n"
    original_policy=b'{"old":"policy"}\n'
    m.WORKER.write_bytes(original_worker)
    m.ROOT_POLICY.write_bytes(original_policy)
    m.FREEZE.write_bytes(b"original-freeze\n")
    worker=b"new-worker\n"
    module=b"projection-module\n"
    source_sha="f"*40
    new_policy={"source_sha":source_sha,"root_worker_sha256":sha256(worker).hexdigest()}
    updated=m.canonical(new_policy)+b"\n"
    plan={"current_protected_main_sha":source_sha,"plan_sha256":"a"*64,
          "updated_root_policy_exactly":new_policy,
          "updated_root_policy_sha256":sha256(updated).hexdigest(),
          "original_freeze_sha256":sha256(m.FREEZE.read_bytes()).hexdigest()}
    manifest={"runtime_image_id":"sha256:"+"1"*64,
              "mcp_image_id":"sha256:"+"2"*64,
              "snapshot_sha":"c"*40}
    (folder/"config"/"catalog-scoped-release-admission.json").write_text(json.dumps(manifest))
    original_live={"jason-runtime":("id1","sha256:"+"3"*64,"start1"),
                   "jason-mcp-pilot":("id2","sha256:"+"4"*64,"start2")}
    monkeypatch.setattr(m,"preflight", lambda:(plan,original_worker,original_policy,
        {str(m.WORKER):worker,str(m.PROJECTION):module},original_live))
    monkeypatch.setattr(m,"auth_owner",lambda p:"bee80bdc-ffb0-4c50-b453-c09d4d411f5f")
    monkeypatch.setattr(m,"verify_accepted_bootstrap_retirement",lambda sha:"verified-retirement-owner")
    monkeypatch.setattr(m,"root_directory",lambda *a,**k:None)
    @contextmanager
    def no_op_lock():
        yield
    monkeypatch.setattr(m,"hold_locks",no_op_lock)
    monkeypatch.setattr(m,"inspect_containers",lambda:original_live)
    monkeypatch.setattr(m,"file",lambda path,**kw:Path(path).read_bytes())
    timer={"active":False,"enabled":False}
    fault={"mcp":False}
    calls=[]
    def execute(*args,**kwargs):
        calls.append(args)
        if args[:3]==("systemctl","disable","--now"):
            timer.update(active=False,enabled=False)
            return ""
        if args[:3]==("systemctl","enable","--now"):
            timer.update(active=True,enabled=True)
            return ""
        if args[0]=="python3" and "--preflight" in args:
            live=args[args.index("--live")+1]
            if fault["mcp"] and live=="jason-mcp-pilot":
                return "PREFLIGHT=DENY"
            return "\n".join(("PREFLIGHT=PASS", "LIVE_CONTAINER="+live,
                              "CANDIDATE_IMAGE_ID="+manifest["runtime_image_id" if live=="jason-runtime" else "mcp_image_id"],
                              "SOURCE_IMAGE_ID="+original_live[live][1],
                              "SET_ENV_COUNT=1", "ADDITIONAL_READONLY_BIND_COUNT=0"))
        raise AssertionError(args)
    monkeypatch.setattr(m,"run",execute)
    def state(action,timer_name):
        if timer_name==m.SCOPED_TIMER:
            return "active" if action=="is-active" else "enabled"
        return ("active" if timer["active"] else "inactive") if action=="is-active" else ("enabled" if timer["enabled"] else "disabled")
    monkeypatch.setattr(m,"systemctl",state)
    def subrun(argv,**kwargs):
        if argv[:2]==("systemctl","is-enabled"):
            return subprocess.CompletedProcess(argv,0 if timer["enabled"] else 1,
                                               "enabled" if timer["enabled"] else "disabled","")
        if argv[:2]==("systemctl","is-active"):
            return subprocess.CompletedProcess(argv,0 if timer["active"] else 3,
                                               "active" if timer["active"] else "inactive","")
        raise AssertionError(argv)
    monkeypatch.setattr(m.subprocess,"run",subrun)
    return original_worker,original_policy,worker,module,updated,timer,fault,calls


def test_exact_root_rebind_success_only_fixed_targets_and_timer(transaction):
    old_worker,old_policy,worker,module,updated,timer,fault,calls=transaction
    m.execute()
    assert m.WORKER.read_bytes()==worker
    assert m.PROJECTION.read_bytes()==module
    assert m.ROOT_POLICY.read_bytes()==updated
    assert not timer["active"] and not timer["enabled"]
    assert (m.LEDGER/"verified.json").is_file()
    proof=json.loads((m.LEDGER/"owner-intent.json").read_text())
    assert proof["action"]==m.ACTION and proof["confirmation"]==m.CONFIRM
    assert proof["source_sha"]=="f"*40
    assert [x for x in calls if x[0]=="python3"] and len([x for x in calls if x[0]=="python3"])==2


def test_exact_root_rebind_rolls_back_after_mcp_preflight_failure(transaction):
    old_worker,old_policy,worker,module,updated,timer,fault,calls=transaction
    fault["mcp"]=True
    with pytest.raises(PermissionError,match="PINNED_NATIVE_PREFLIGHT_FAILED"):
        m.execute()
    assert m.WORKER.read_bytes()==old_worker
    assert m.ROOT_POLICY.read_bytes()==old_policy
    assert not m.PROJECTION.exists()
    assert not timer["active"] and not timer["enabled"]
    assert json.loads((m.LEDGER/"failed.json").read_text())["rollback_verified"] is True
    assert not (m.LEDGER/"verified.json").exists()


def test_entra_device_flow_uses_exact_rfc_grant_type_without_network(monkeypatch, capsys):
    """Regression: underscore in grant_type was rejected before Owner confirmation."""
    from types import SimpleNamespace

    calls = []
    fake = SimpleNamespace(
        TENANT="synthetic-tenant", CLIENT_ID="synthetic-client", SCOPE="Jason.Read",
        jwt_owner=lambda token: "synthetic-verified-owner"
    )
    def only_synthetic_response(url, args):
        calls.append((url, dict(args)))
        if url.endswith("/devicecode"):
            return {"device_code": "never-real-device-code",
                    "user_code": "synthetic-display-code",
                    "verification_uri": "https://login.microsoft.com/device",
                    "expires_in": 600, "interval": 5}
        assert url.endswith("/token")
        if args["grant_type"] != "urn:ietf:params:oauth:grant-type:device_code":
            return {"error": "invalid_request"}
        assert args["device_code"] == "never-real-device-code"
        assert args["client_id"] == "synthetic-client"
        return {"access_token": "synthetic-never-real-access-token"}
    fake._form = only_synthetic_response
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None))
    monkeypatch.setattr(m.importlib.util, "spec_from_file_location", lambda *a: spec)
    monkeypatch.setattr(m.importlib.util, "module_from_spec", lambda spec: fake)
    monkeypatch.setattr(m, "file", lambda *a, **kw: b"synthetic-checked-pinned-verifier")
    monkeypatch.setattr(m, "digest", lambda data: m.OWNER_HELPER_SHA)
    monkeypatch.setattr("builtins.input", lambda prompt: m.CONFIRM)
    approved = m.auth_owner({"current_protected_main_sha": "a"*40,
                             "plan_sha256": "b"*64})
    assert approved == "synthetic-verified-owner"
    assert [u.rsplit("/",1)[-1] for u,_ in calls] == ["devicecode", "token"]
    assert calls[1][1]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert "synthetic-never-real-access-token" not in capsys.readouterr().out


def test_entra_owner_confirmation_remains_mandatory(monkeypatch):
    from types import SimpleNamespace
    fake = SimpleNamespace(
        TENANT="synthetic-tenant", CLIENT_ID="synthetic-client", SCOPE="Jason.Read",
        jwt_owner=lambda token: "synthetic-verified-owner")
    fake._form = lambda url, args: (
        {"device_code": "no-real-code", "user_code": "synthetic",
         "verification_uri": "https://login.microsoft.com/device",
         "expires_in": 600, "interval": 5}
        if url.endswith("/devicecode") else {"access_token": "synthetic-never-real-token"})
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None))
    monkeypatch.setattr(m.importlib.util, "spec_from_file_location", lambda *a: spec)
    monkeypatch.setattr(m.importlib.util, "module_from_spec", lambda spec: fake)
    monkeypatch.setattr(m, "file", lambda *a, **kw: b"synthetic-pinned-verifier")
    monkeypatch.setattr(m, "digest", lambda data: m.OWNER_HELPER_SHA)
    monkeypatch.setattr("builtins.input", lambda prompt: "NOT APPROVED")
    with pytest.raises(PermissionError, match="EXACT_OWNER_CONFIRMATION_MISSING"):
        m.auth_owner({"current_protected_main_sha": "a"*40, "plan_sha256": "b"*64})
