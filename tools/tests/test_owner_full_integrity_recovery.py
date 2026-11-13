"""Synthetic fail-closed tests for one-shot signed full SQLite proof recovery."""
from __future__ import annotations
import importlib.util
import json
import os
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[2]


def m():
    p=ROOT/"tools"/"owner_full_integrity_recovery.py"
    s=importlib.util.spec_from_file_location("owner_full_integrity_recovery",p)
    x=importlib.util.module_from_spec(s)
    s.loader.exec_module(x)
    return x


def valid(tmp_path, monkeypatch, module):
    p=tmp_path/"full.json"
    r={
        "status":"pass","failures":[],"snapshot_source_exit_code":0,
        "provider_contacted":False,"provider_credentials_used":False,
        "delegations":{"expired_active_records":0},
        "trusted_key_registry":{"present":True,"mode":"0o600","active_records":1},
        "files":{
            "authority":{"path":"/var/lib/jason/authority/authority.sqlite3",
                         "present":True,"integrity":"ok","mode":"0o600"},
            "replay":{"path":"/var/lib/jason/openclaw/replay.sqlite3",
                      "present":True,"integrity":"ok","mode":"0o600"},
            "security_audit":{"path":"/var/lib/jason/openclaw/security-audit.sqlite3",
                              "present":True,"integrity":"ok","mode":"0o600"},
            "orchestration_audit":{"path":"/var/lib/jason/openclaw/orchestration-events.sqlite3",
                                   "present":True,"integrity":"ok","mode":"0o600"},
        },
        "backup_restore_proof":{
            "backup_integrity":"ok","restore_integrity":"ok",
            "backup_mode":"0o600","restore_mode":"0o600",
            "counts_match":True,
        }
    }
    p.write_text(json.dumps(r))
    p.chmod(0o600)
    monkeypatch.setattr(module,"FULL",p)
    monkeypatch.setattr(module,"AL_UID",os.geteuid())
    return p,r


def test_full_proof_requires_all_four_actual_sqlite_integrity_checks(monkeypatch,tmp_path):
    x=m();p,r=valid(tmp_path,monkeypatch,x)
    assert x.valid_full_proof(time.time()-20)=={
        "integrity":True,"backup_restore":True,"full_result_recorded":True}
    assert set(r["files"])=={"authority","replay","security_audit","orchestration_audit"}


@pytest.mark.parametrize("path,value",[
    ("status","fail"),("snapshot_source_exit_code",124),
    ("provider_contacted",True),("provider_credentials_used",True),
    ("files.authority.integrity","not_run"),
    ("files.orchestration_audit.integrity","not_run"),
    ("files.replay.mode","0o644"),
    ("files.security_audit.present",False),
    ("backup_restore_proof.counts_match",False),
    ("backup_restore_proof.restore_integrity","failed"),
    ("backup_restore_proof.backup_mode","0o644"),
    ("trusted_key_registry.active_records",0),
    ("delegations.expired_active_records",1),
])
def test_full_proof_refuses_partial_stale_or_forged_pass(monkeypatch,tmp_path,path,value):
    x=m();p,r=valid(tmp_path,monkeypatch,x)
    obj=r
    parts=path.split(".")
    for key in parts[:-1]:obj=obj[key]
    obj[parts[-1]]=value
    p.write_text(json.dumps(r))
    with pytest.raises(x.RecoveryDenied):
        x.valid_full_proof(time.time()-20)


def test_proof_time_and_permissions_not_waived(monkeypatch,tmp_path):
    x=m();p,_=valid(tmp_path,monkeypatch,x)
    with pytest.raises(x.RecoveryDenied,match="FRESH_FULL_PROOF"):
        x.valid_full_proof(time.time()+100)
    p.chmod(0o644)
    with pytest.raises(x.RecoveryDenied,match="FRESH_FULL_PROOF"):
        x.valid_full_proof(time.time()-100)


def test_owner_exact_action_no_token_output(monkeypatch,capsys):
    x=m()
    def req(url,body):
        if url.endswith("/devicecode"):
            return {"device_code":"private-device-code","user_code":"EXACT-CODE",
                    "verification_uri":"https://login.microsoftonline.com/device",
                    "expires_in":300,"interval":5}
        assert "private-device-code" in body.values()
        return {"access_token":"private-verified-access-token"}
    owner=SimpleNamespace(
        TENANT="fake-tenant",CLIENT_ID="fake-client",SCOPE="read-scope",
        _form=req,jwt_owner=lambda token:("verified-oid" if token=="private-verified-access-token"
                                        else pytest.fail("invalid bearer token")),
    )
    monkeypatch.setattr(x.time,"sleep",lambda s:None)
    assert x.interactive_exact_owner(owner)=="verified-oid"
    output=capsys.readouterr().out
    assert "EXACT_ACTION="+x.ACTION in output
    assert "MAY_CONSUME_HOST_CPU_DISK_FOR_UP_TO_90_MINUTES=true" in output
    assert "private-device-code" not in output
    assert "private-verified-access-token" not in output


@pytest.mark.parametrize("response",[
    {"error":"invalid_client"},
    {"device_code":"c","user_code":"d","verification_uri":"url","expires_in":1},
])
def test_owner_device_flow_refuses_invalid_challenge(monkeypatch,response):
    x=m();owner=SimpleNamespace(
        TENANT="synthetic",CLIENT_ID="synthetic",SCOPE="read",
        _form=lambda url,body:response,
    )
    with pytest.raises(x.RecoveryDenied):
        x.interactive_exact_owner(owner)


def test_exact_root_source_policy_and_command_only(monkeypatch):
    x=m()
    assert x.LKG=="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
    assert x.DURATION==5400 and x.SUPERVISOR_SECONDS==5700
    assert x.ROOT_SCRIPT.parent==Path("/usr/local/lib/jason")
    assert x.SNAPSHOT.parent==x.CHECKER.parent
    assert x.ACTION.endswith("recovery-v1")
    s=(ROOT/"tools"/"owner_full_integrity_recovery.py").read_text()
    assert "jason-runtime" in s and "jason-mcp-pilot" in s
    assert "START=" not in s
    assert "systemctl\",\"reset-failed" in s
    assert "read_only" not in s or "READ_ONLY" in s


def test_root_execution_cannot_run_from_mutable_worktree():
    x=m()
    with pytest.raises(x.RecoveryDenied,match="ROOT_ISOLATED_PYTHON_REQUIRED"):
        x.recover_once()


def test_root_exact_policy_rejects_unexpected_key(monkeypatch):
    x=m()
    policy={
        "schema_version":"1.0", "exact_action":x.ACTION,"one_shot":True,
        "lkg_sha":x.LKG,"runtime_image":x.RUNTIME_IMAGE,"mcp_image":x.MCP_IMAGE,
        "freeze_sha256":x.FREEZE_SHA,
        "scan_timeout_seconds":x.DURATION,
        "supervisor_timeout_seconds":x.SUPERVISOR_SECONDS,
        "scope":x.APPROVAL_SCOPE,
        "source_script_sha256":"a"*64,"snapshot_sha256":"b"*64,
        "checker_sha256":"c"*64,"trusted_owner_auth_sha256":"d"*64,
        "unexpected_enable_approval_bypass":True,
    }
    monkeypatch.setattr(x,"secure_file",lambda path,**kw: json.dumps(policy).encode())
    with pytest.raises(x.RecoveryDenied,match="ROOT_EXACT_POLICY_SHAPE_MISMATCH"):
        x.source_verification()


def test_run_claim_is_exclusive_and_root_owned(monkeypatch,tmp_path):
    x=m();p=tmp_path/"once.json"
    monkeypatch.setattr(x.os,"fchown",lambda *args:None)
    x.root_record(p,{"state":"claimed"})
    assert stat.S_IMODE(p.stat().st_mode)==0o600
    with pytest.raises(FileExistsError):
        x.root_record(p,{"state":"duplicate"})


def test_full_recovery_requires_closed_native_control_only_after_actual_proof():
    x=m()
    code=(ROOT/"tools"/"owner_full_integrity_recovery.py").read_text()
    assert code.index("valid_full_proof(start)")<code.index("systemctl\",\"reset-failed")
    assert code.index("systemctl\",\"start\",DRIFT_SERVICE")>code.index("with production_lock()")
    assert "r.revalidate_circuit_breaker(" in code
    assert "if proc.returncode" not in code
    assert "Popen(" in code and "killpg(" in code


def test_no_provider_write_no_unrelated_runtime_start():
    x=m()
    code=(ROOT/"tools"/"owner_full_integrity_recovery.py").read_text()
    assert "jason-constant-contact-reconcile.timer" not in code
    assert '["docker", "stop"' not in code
    assert '["docker", "restart"' not in code
    assert '["docker", "rm"' not in code
    assert "JASON_CONSTANT_CONTACT_IMPORT_PROFILE=" not in code
    assert "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true" not in code
    assert "AUTHORIZED_BY_TEAMS" not in code



def test_timeout_terminates_only_owned_process_group(monkeypatch):
    x=m();signals=[]
    class Fake:
        pid=23456
        def wait(self,timeout):
            return 0
    monkeypatch.setattr(x.os,"killpg",lambda pid,sig:signals.append((pid,sig)))
    x.terminate_scan_process_group(Fake())
    assert signals==[(23456,x.signal.SIGTERM)]


def test_stubborn_scan_process_group_is_killed_after_bound(monkeypatch):
    x=m();signals=[]
    class Fake:
        pid=34567
        calls=0
        def wait(self,timeout):
            self.calls+=1
            if self.calls==1:
                raise subprocess.TimeoutExpired(cmd="private-source",timeout=timeout)
            return 0
    monkeypatch.setattr(x.os,"killpg",lambda pid,sig:signals.append((pid,sig)))
    x.terminate_scan_process_group(Fake())
    assert signals==[(34567,x.signal.SIGTERM),(34567,x.signal.SIGKILL)]


def test_expired_allowance_is_not_renewed_or_ignored():
    x=m()
    code=(ROOT/"tools"/"owner_full_integrity_recovery.py").read_text()
    assert "owner-emergency-full-proof-degraded.conf" not in code
    assert "TimeoutStartSec" not in code
    assert "full_integrity_proof_missing_stale_or_invalid" not in code
    assert "jason-openclaw-authority-health.service" in code
    assert "jason-production-drift-watchdog.service" in code
    assert "subprocess.Popen(" in code
    assert "terminate_scan_process_group(proc)" in code
