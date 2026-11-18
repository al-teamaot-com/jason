"""PMv4 D exact read-only service install: fail-closed scoped semantics."""
import json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import sqlite3
import pytest

from tools import pmv4_d_runbook_read_install_root as root
from tools import pmv4_d_runbook_read_install_builder as builder


def policy(base):
    return (json.dumps(base,sort_keys=True,indent=2)+"\n").encode()


def test_one_unit_allowance_preserves_every_other_guard_and_freeze():
    previous={
        "schema_version":"1.0",
        "required_containers":["jason-runtime","jason-mcp-pilot"],
        "allowed_running_containers":["jason-runtime","jason-pmv4-ticket-core"],
        "required_system_units":["jason-production-drift-watchdog.timer"],
        "allowed_system_units":["jason-boot-recovery.service","jason-runtime.service"],
        "required_user_units":["jason-release-manager.timer"],
        "max_stopped_rollback_containers":21,
        "forbidden_execution_prefixes":["/unapproved"],
    }
    data=policy(previous)
    next_bytes=root.proposed_policy(data)
    next_obj=json.loads(next_bytes)
    changed={k for k in previous if previous[k]!=next_obj[k]}
    assert changed=={"allowed_system_units"}
    assert next_obj["allowed_system_units"]==[
        "jason-boot-recovery.service",root.UNIT,"jason-runtime.service"]
    assert next_obj["max_stopped_rollback_containers"]==21
    assert next_obj["required_containers"]==previous["required_containers"]
    assert root.sha(next_bytes)!=root.sha(data)
    with pytest.raises(root.RunbookInstallDenied,match="BASELINE_UNIT_ALREADY_PRESENT"):
        root.proposed_policy(next_bytes)


def test_oneuse_root_production_entrypoint_is_unavailable_to_unprivileged_user(tmp_path):
    with pytest.raises(root.RunbookInstallDenied,match="ROOT_ISOLATED_ONLY"):
        root.packet(tmp_path/"not-root-approved.json")


def test_protected_scope_has_no_bypass_or_other_runtime_mutations():
    assert root.ACTION=="pmv4-d-one-owner-independent-runbook-read-install-v1"
    assert root.CONFIRM=="APPROVE-EXACT-PMV4-D-INDEPENDENT-RUNBOOK-READ-INSTALL"
    assert root.REGISTRY==Path("/var/lib/jason/openclaw/json-playbooks.sqlite3")
    assert root.UNIT=="jason-runbook-management-read.service"
    assert root.FILES==(
        "implementation/autonomous_remediation/__init__.py",
        "implementation/autonomous_remediation/playbook_document.py",
        "implementation/autonomous_remediation/playbook_store.py",
        "implementation/autonomous_remediation/runbook_management_read_service.py",
        "infrastructure/pmv4-runbook-management/jason-runbook-management-read.service",
    )
    code=Path(root.__file__).read_text()
    for required in ('verified_stage_c()', 'native_drift(POLICY)',
                     'status_core()==initial','systemctl("enable","--now",UNIT',
                     'systemctl("disable","--now",UNIT','rollback_verified',
                     'REGISTRY_WRITES' if 'REGISTRY_WRITES' in code else 'registry_writes'):
        assert required in code
    assert 'docker restart' not in code and 'docker stop' not in code
    assert 'reset-failed' not in code and 'systemctl("mask"' not in code
    assert 'circuit_breaker"]["state"] = "closed"' not in code


def test_service_unit_is_readonly_no_network_no_provider_authority():
    p=Path(__file__).resolve().parents[1] / root.FILES[-1]
    raw=p.read_text()
    assert "User=al" in raw and "Group=al" in raw
    assert "Restart=on-failure" in raw
    assert "RestrictAddressFamilies=AF_UNIX" in raw
    assert "IPAddressDeny=any" in raw
    assert "ProtectSystem=strict" in raw
    assert "PrivateTmp=true" in raw
    assert "NoNewPrivileges=true" in raw
    assert "ReadOnlyPaths=/var/lib/jason/openclaw/json-playbooks.sqlite3" in raw
    assert "ReadWritePaths=/run/jason-runbook-management" in raw
    assert "WorkingDirectory=/usr/local/lib/jason/runbook-management/current" in raw
    assert "ExecStart=/usr/bin/python3 -m autonomous_remediation.runbook_management_read_service" in raw
    assert "CapabilityBoundingSet=CAP_SYS_ADMIN" not in raw


def test_stage_c_root_accepted_receipt_is_required(monkeypatch):
    fixture={"status":"postmigration_stage_c_accepted",
             "approval_id":root.STAGE_C_APPROVAL,
             "candidate_sha":root.STAGE_C_SHA,
             "no_database_relocation":True,"mcp_restarts":0,
             "scan_cycle_ids":["scan-one","scan-two"]}
    monkeypatch.setattr(root,"trusted_read",lambda *args,**kw:root.canon(fixture))
    root.verified_stage_c()
    for key,bad in (
        ("status","rollback"),
        ("candidate_sha","0"*40),
        ("mcp_restarts",1),
        ("scan_cycle_ids",["same","same"]),
        ("no_database_relocation",False),
    ):
        changed=dict(fixture)
        changed[key]=bad
        monkeypatch.setattr(root,"trusted_read",
                            lambda *a,doc=changed,**kw:root.canon(doc))
        with pytest.raises(root.RunbookInstallDenied,
                           match="STAGE_C_ROOT_ACCEPTANCE_NOT_VERIFIED"):
            root.verified_stage_c()


def test_native_drift_failure_is_never_a_success(monkeypatch):
    mock=SimpleNamespace(returncode=2,stdout=json.dumps({
        "status":"drift_detected",
        "problems":[{"kind":"undeclared_running_system_unit"}]}))
    monkeypatch.setattr(root,"run",lambda *a,**kw:mock)
    with pytest.raises(root.RunbookInstallDenied,match="NATIVE_DRIFT_GUARD_FAILED"):
        root.native_drift(Path("/exact/pinned.json"))
    mock.returncode=0
    with pytest.raises(root.RunbookInstallDenied,match="NATIVE_DRIFT_NOT_PASS"):
        root.native_drift(Path("/exact/pinned.json"))
    mock.stdout='{"status":"pass","problems":[]}'
    root.native_drift(Path("/exact/pinned.json"))


def test_last_ticket_scan_must_be_fresh_duplicate_free(tmp_path,monkeypatch):
    p=tmp_path/"ledger.sqlite3"
    with sqlite3.connect(p) as db:
        db.execute("""CREATE TABLE autonomy_ticket_scan_cycle (
            scanned_at TEXT,provider_items INTEGER,duplicate_items INTEGER)""")
        db.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?)",
            ((datetime.now(timezone.utc)-timedelta(seconds=25)).isoformat(),140,0))
        db.commit()
    real_path=Path
    # Synthetic approval reads only a temporary ledger.
    class FakePath:
        def __new__(cls,raw):
            if str(raw)=="/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3":
                return p
            return real_path(raw)
    monkeypatch.setattr(root,"Path",FakePath)
    assert root.verify_recent_ticket_scan()
    with sqlite3.connect(p) as db:
        db.execute("UPDATE autonomy_ticket_scan_cycle SET duplicate_items=1")
        db.commit()
    with pytest.raises(root.RunbookInstallDenied,match="TICKET_SCAN_NOT_ACCEPTED"):
        root.verify_recent_ticket_scan()


def test_builder_rejects_symlink_source_file_without_git_access(monkeypatch):
    def fake_git(*args):
        if args[0]=="ls-tree":
            return (("120000 blob "+"a"*40+"\t"+args[-1]+"\n").encode())
        raise AssertionError("Cannot proceed from Git symlink")
    monkeypatch.setattr(builder,"git",fake_git)
    with pytest.raises(builder.StageDBuilderDenied,
                       match="SOURCE_BLOB_NOT_PLAIN_FILE"):
        builder.reviewed_blob("a"*40,root.FILES[0])


def test_root_owner_proof_is_exact_action_and_not_teams_or_impersonation():
    source=Path(root.__file__).read_text()
    assert 'lib.jwt_owner(value["access_token"])' in source
    assert "urn:ietf:params:oauth:grant-type:device_code" in source
    assert root.CONFIRM in source or "CONFIRM" in source
    assert "teams_required" not in source.lower()
    assert "owner_consumed_before_mutation" in source
    assert "production_mutations" in source


def test_package_launcher_is_inert_in_check_only(tmp_path):
    data={"source_sha":"a"*40,"root_sha256":"b"*64}
    launcher=builder.launcher(tmp_path,data).decode()
    assert '[[ "$MODE" == "--check-only" ]] && exit 0' in launcher
    assert "sudo /usr/bin/install" in launcher
    assert "--plan \"$P\" --check-only" in launcher
    assert "PMV4_D_EXACT_RUNBOOK_SERVICE_INSTALL_AND_READBACK=PASS" in launcher
    assert "ROOT_SHA" not in launcher


@pytest.fixture
def fake_root_transaction(tmp_path,monkeypatch):
    """Exercise the same production function with every external call inert."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    p={
        "source_sha":"a"*40,"scope_sha256":"b"*64,
        "freeze_sha256":root.sha(b"freeze"),
        "policy_base_sha256":root.sha(b"before"),
        "policy_target_sha256":root.sha(b"after"),
    }
    artifact=tmp_path/"artifact"
    artifact.mkdir()
    live={"policy":b"before","drift_failure":False}
    actions=[]
    auditroot=tmp_path/"root-ledger"
    monkeypatch.setattr(root,"AUDIT",auditroot)
    stat_lstat=Path.lstat
    def synthetic_lstat(path):
        out=stat_lstat(path)
        if path==auditroot:
            return SimpleNamespace(st_uid=0,st_mode=out.st_mode)
        return out
    monkeypatch.setattr(Path,"lstat",synthetic_lstat)
    monkeypatch.setattr(root.os,"isatty",lambda fd:True)
    monkeypatch.setattr(root,"packet",lambda path:(p,artifact))
    monkeypatch.setattr(root,"verify",lambda x,y:({"runtime":"unchanged"},
                                                  {"registry_generation":0,"rows":0}))
    monkeypatch.setattr(root,"authenticated_owner",lambda x:"verified-oid-from-entra")
    @contextmanager
    def fake_locks():
        actions.append("locks")
        yield
    monkeypatch.setattr(root,"locks",fake_locks)
    def reading(path,**kw):
        if path==artifact/"policy-base.json":return b"before"
        if path==artifact/"policy-target.json":return b"after"
        if path==root.POLICY:return live["policy"]
        if path==root.CONTROL:return b'{"circuit_breaker":{"state":"closed"}}'
        if path==root.FREEZE:return b"freeze"
        raise AssertionError("Unexpected read "+str(path))
    monkeypatch.setattr(root,"trusted_read",reading)
    def install(p,a): actions.append("install_readonly_files")
    monkeypatch.setattr(root,"install_files",install)
    def writepolicy(target,expected):
        assert live["policy"]==expected
        live["policy"]=target
        actions.append("policy_update")
    monkeypatch.setattr(root,"atomic_policy",writepolicy)
    def ctl(*args,**kwargs):
        actions.append("systemctl_"+"_".join(args))
        return SimpleNamespace(stdout="active")
    monkeypatch.setattr(root,"systemctl",ctl)
    monkeypatch.setattr(root,"service_readback",lambda:{
        "status":"healthy","registry_generation":0,"active_count":0,
        "provider_calls":False,"execution_authority":False,
        "configuration_mutations":False,
    })
    monkeypatch.setattr(root,"verify_recent_ticket_scan",lambda:"2026-11-18T12:00:00+00:00")
    def drift(*args):
        actions.append("native_drift")
        if live["drift_failure"]:
            raise root.RunbookInstallDenied("PMV4_D_SYNTHETIC_DRIFT_FAILED")
    monkeypatch.setattr(root,"native_drift",drift)
    monkeypatch.setattr(root,"status_core",lambda:{"runtime":"unchanged"})
    monkeypatch.setattr(root,"remove_own_files",lambda:actions.append("remove_only_service_files"))
    monkeypatch.setattr(root,"audit",lambda path,document:
                        path.write_bytes(root.canon(document)))
    return tmp_path/"plan.json",auditroot,actions,live,p


def test_root_success_writes_exact_acceptance_only_after_native_drift(fake_root_transaction):
    path,auditroot,actions,live,p=fake_root_transaction
    root.execute(path)
    assert live["policy"]==b"after"
    assert "systemctl_enable_--now_"+root.UNIT in actions
    assert actions.count("native_drift")==2
    assert "systemctl_start_jason-production-drift-watchdog.service" in actions
    assert not any("jason-runtime" in s or "jason-mcp-pilot" in s
                   for s in actions)
    accepted=json.loads((auditroot/(p["source_sha"]+"-accepted.json")).read_text())
    assert accepted["status"]=="independent_runbook_read_service_accepted"
    assert accepted["provider_writes"]==0
    assert accepted["ticket_core_restarts"]==0
    assert accepted["mcp_restarts"]==0
    assert accepted["production_freeze_unchanged"] is True
    assert not (auditroot/(p["source_sha"]+"-rollback.json")).exists()
    with pytest.raises(root.RunbookInstallDenied,match="OWNER_ACTION_ALREADY_CONSUMED"):
        root.execute(path)


def test_native_drift_failure_reverts_unit_and_policy(fake_root_transaction):
    path,auditroot,actions,live,p=fake_root_transaction
    live["drift_failure"]=True
    with pytest.raises(root.RunbookInstallDenied,match="SYNTHETIC_DRIFT_FAILED"):
        root.execute(path)
    assert live["policy"]==b"before"
    assert "systemctl_disable_--now_"+root.UNIT in actions
    assert "remove_only_service_files" in actions
    assert "systemctl_daemon-reload" in actions
    assert "systemctl_enable_--now_"+root.UNIT in actions
    assert not any("runtime" in s or "mcp" in s for s in actions)
    result=json.loads((auditroot/(p["source_sha"]+"-rollback.json")).read_text())
    assert result["rollback_verified"] is False  # simulated drift remains injected
    assert not (auditroot/(p["source_sha"]+"-accepted.json")).exists()


def test_native_drift_failure_can_be_reverified_after_rollback(fake_root_transaction,monkeypatch):
    path,auditroot,actions,live,p=fake_root_transaction
    original=root.native_drift
    calls=[]
    def fail_once(path):
        calls.append(bytes(live["policy"]))
        if live["policy"]==b"after":
            raise root.RunbookInstallDenied("PMV4_D_SYNTHETIC_DRIFT_FAILED")
    monkeypatch.setattr(root,"native_drift",fail_once)
    with pytest.raises(root.RunbookInstallDenied,match="SYNTHETIC_DRIFT_FAILED"):
        root.execute(path)
    assert calls==[b"after",b"before"]
    assert live["policy"]==b"before"
    outcome=json.loads((auditroot/(p["source_sha"]+"-rollback.json")).read_text())
    assert outcome["status"]=="rolled_back"
    assert outcome["rollback_verified"] is True


def test_actual_owner_uid_socket_readback_uses_valid_inline_python(tmp_path,monkeypatch):
    """Prevent a root-only postflight typo from burning another Owner approval."""
    import os
    import socket
    import subprocess
    import sys
    import time
    from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
    registry=tmp_path/"json-playbooks.sqlite3"
    store=SQLitePlaybookRegistry(registry)
    store.close()
    socket_path=tmp_path/"read.sock"
    runner=subprocess.Popen(
        [sys.executable,"-m","autonomous_remediation.runbook_management_read_service",
         "--registry",str(registry),"--socket",str(socket_path)],
        env={**os.environ,"PYTHONPATH":"implementation"},
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
    )
    try:
        for n in range(100):
            if socket_path.is_socket():break
            if runner.poll() is not None:
                raise AssertionError(runner.stderr.read()[:300])
            time.sleep(0.03)
        else: raise AssertionError("socket not ready")
        original_path=Path
        monkeypatch.setattr(root,"Path",
            lambda x: socket_path if str(x)=="/run/jason-runbook-management/read.sock"
            else original_path(x))
        def systemctl(*a,**kw):
            assert a[0] in ("is-active","is-enabled")
            return SimpleNamespace(stdout="active\n" if a[0]=="is-active" else "enabled\n")
        monkeypatch.setattr(root,"systemctl",systemctl)
        def fake_run(args,**kw):
            assert args[:2]==["/usr/bin/python3","-c"]
            assert kw.get("user") is True
            # Already running under same uid as service; do not use sudo.
            return subprocess.run(args,capture_output=True,text=True,timeout=10,check=True)
        monkeypatch.setattr(root,"run",fake_run)
        received=root.service_readback()
        assert received["status"]=="healthy"
        assert received["registry_generation"]==0
        assert received["active_count"]==0
        assert received["provider_calls"] is False
    finally:
        runner.terminate()
        try:runner.communicate(timeout=3)
        except subprocess.TimeoutExpired:runner.kill();runner.communicate()
