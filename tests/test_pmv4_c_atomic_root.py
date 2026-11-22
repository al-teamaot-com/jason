from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pytest

from tools import pmv4_c_atomic_root as root
from tools import pmv4_c_service_manifest as svc

SOURCE="a"*40
ROLLBACK="b"*40
IMAGE="sha256:"+"c"*64

def minimal_plan(tmp_path:Path):
    artifact=tmp_path/("pmv4-c-"+SOURCE)
    artifact.mkdir()
    plan={
        "schema_version":"1.0","action":root.ACTION,
        "candidate_sha":SOURCE,"rollback_sha":ROLLBACK,
        "production_lkg_sha":ROLLBACK,
        "worker_image_digest":IMAGE,
        "runtime_container_id":"r"*64,
        "mcp_container_id":"m"*64,
        "runtime_image_digest":"sha256:"+"d"*64,
        "mcp_image_digest":"sha256:"+"e"*64,
        "freeze_sha256":"f"*64,"hold_sha256":"1"*64,
        "watchdog_path":str(root.WATCHDOG),
        "watchdog_base_sha256":"2"*64,
        "watchdog_candidate_sha256":"3"*64,
        "service_manifest_sha256":"4"*64,
        "root_executor_sha256":"5"*64,
        "owner_issuer_sha256":"6"*64,
        "staged_source_files":{},
        "db_identities":{},"credential_paths":[],
        "provider_state_metadata":{},
        "runtime_env_overrides":dict(root.RUNTIME_ENV_OVERRIDES),
        "mcp_env_overrides":dict(root.MCP_ENV_OVERRIDES),
        "service_restarts":["jason-runtime","jason-mcp-pilot"],
        "normal_ticket_processing_after_activation":True,
        "two_scan_acceptance":True,"owner_consents":1,
        "standing_authority":False,"later_stages_authorized":False,
        "baseline_scan_cycle_id":"scan-before-build",
        "baseline_scanned_at":"2026-11-17T00:00:00+00:00",
    }
    plan["scope_sha256"]=root.sha(root.canon(plan))
    path=artifact/"root-release-plan.json"
    path.write_bytes(root.canon(plan))
    return path,plan

def test_plan_binds_one_owner_restarts_and_exact_env(tmp_path):
    path,plan=minimal_plan(tmp_path)
    assert root._plan(path)==plan
    bad=dict(plan);bad["runtime_env_overrides"]=dict(plan["runtime_env_overrides"])
    bad["runtime_env_overrides"]["JASON_TICKET_WORKER_HOSTING"]="embedded"
    unsigned=dict(bad);unsigned.pop("scope_sha256")
    bad["scope_sha256"]=root.sha(root.canon(unsigned))
    path.write_bytes(root.canon(bad))
    with pytest.raises(root.StageCRootDenied,match="SCHEMA_OR_AUTHORITY_NOT_EXACT"):
        root._plan(path)

def test_worker_create_has_no_ports_and_exact_hardening():
    manifest={
        "user":"1000:1000","restart_policy":"unless-stopped",
        "memory_bytes":svc.MEMORY_BYTES,"pids_limit":svc.PIDS_LIMIT,
        "network_mode":"jason-core","environment":{"JASON_X":"1"},
        "mounts":[{"Source":"/a","Destination":"/b","RW":False,"Type":"bind"}],
        "labels":{"com.aot.jason.component":"pmv4-ticket-core"},
        "healthcheck":{
            "test":["CMD-SHELL","python -m jason_runtime.ticket_worker_health"],
            "interval_ns":30_000_000_000,"timeout_ns":5_000_000_000,
            "retries":3,"start_period_ns":120_000_000_000,
        },
        "image_digest":IMAGE,"command":list(svc.COMMAND),
    }
    cmd=root._worker_create(manifest)
    assert cmd[:4]==["/usr/bin/docker","create","--name",root.WORKER]
    assert "--publish" not in cmd and "-p" not in cmd
    assert cmd.count("--cap-drop")==1 and "ALL" in cmd
    assert "--read-only" in cmd and "--privileged" not in cmd
    assert cmd[-3:]==list(svc.COMMAND)
    assert "type=bind,src=/a,dst=/b,readonly" in cmd

def test_clone_command_only_adds_exact_rw_roots(monkeypatch):
    def fake(**kwargs):
        return (
            ["docker","create","--name",kwargs["live"],
             "sha256:"+"d"*64],
            {"JASON_X":"old"},["jason-observability"],
            {"Mounts":[{"Destination":"/var/lib/jason/openclaw"}]},
        )
    monkeypatch.setattr(root.clone,"_build_create_command",fake)
    plan={
        "runtime_image_digest":"sha256:"+"d"*64,
        "mcp_image_digest":"sha256:"+"e"*64,
        "production_lkg_sha":ROLLBACK,
    }
    cmd,env,secondary=root._clone_command(
        plan,"old-runtime","jason-runtime","runtime",
        {"JASON_X":"new"},(Path("/ticket"),Path("/shared")))
    assert cmd[0]=="/usr/bin/docker"
    assert cmd[cmd.index("--name")+1]=="jason-runtime"
    assert "type=bind,src=/ticket,dst=/ticket" in cmd
    assert "type=bind,src=/shared,dst=/shared" in cmd
    assert cmd[-1]==plan["runtime_image_digest"]
    assert secondary==["jason-observability"]

def test_watchdog_transition_is_only_one_allowed_container(tmp_path,monkeypatch):
    path,plan=minimal_plan(tmp_path)
    base={
        "schema_version":"1.0",
        "allowed_running_containers":["jason-runtime","jason-mcp-pilot",
                                      "jason-pmv4-shadow-gateway"],
    }
    base_raw=(json.dumps(base,indent=2)+"\n").encode()
    candidate=json.loads(json.dumps(base))
    candidate["allowed_running_containers"].append(root.WORKER)
    candidate_raw=(json.dumps(candidate,indent=2)+"\n").encode()
    active=tmp_path/"active.json";active.write_bytes(base_raw)
    (path.parent/"production-desired-state.base.json").write_bytes(base_raw)
    (path.parent/"production-desired-state.stage-c.json").write_bytes(candidate_raw)
    plan["watchdog_base_sha256"]=root.sha(base_raw)
    plan["watchdog_candidate_sha256"]=root.sha(candidate_raw)
    unsigned=dict(plan);unsigned.pop("scope_sha256")
    plan["scope_sha256"]=root.sha(root.canon(unsigned))
    path.write_bytes(root.canon(plan))
    monkeypatch.setattr(root,"WATCHDOG",active)
    assert root._watchdog_candidate(path,plan)==candidate_raw
    candidate["allowed_running_containers"].append("foreign")
    foreign=(json.dumps(candidate,indent=2)+"\n").encode()
    (path.parent/"production-desired-state.stage-c.json").write_bytes(foreign)
    plan["watchdog_candidate_sha256"]=root.sha(foreign)
    with pytest.raises(root.StageCRootDenied,match="SINGLE_ADDITION"):
        root._watchdog_candidate(path,plan)

def test_two_scan_acceptance_requires_provider_items_and_zero_duplicates(
    tmp_path,monkeypatch
):
    target=tmp_path/"ticket-core";target.mkdir()
    db=target/"autonomy-operational-work.sqlite3"
    con=sqlite3.connect(db)
    con.execute(
        "CREATE TABLE autonomy_ticket_scan_cycle("
        "cycle_id TEXT PRIMARY KEY,scanned_at TEXT,pages_traversed INTEGER,"
        "provider_items INTEGER,duplicate_items INTEGER,evaluated INTEGER)")
    rows=[
        ("bad","2026-11-17T10:01:00+00:00",4,150,1,149),
        ("good1","2026-11-17T10:02:00+00:00",4,150,0,149),
        ("good2","2026-11-17T10:03:00+00:00",4,151,0,150),
    ]
    con.executemany("INSERT INTO autonomy_ticket_scan_cycle VALUES(?,?,?,?,?,?)",rows)
    con.commit();con.close()
    monkeypatch.setattr(root,"TICKET_TARGET",target)
    accepted=root._wait_two_scans(
        "2026-11-17T10:00:00+00:00",seconds=1)
    assert [r[0] for r in accepted]==["good1","good2"]

def test_root_source_contains_postwrite_no_stale_restore_contract():
    source=Path(root.__file__).read_text()
    assert "new_writer_admitted=True" in source
    assert "rolled_back_to_embedded_new_canonical" in source
    assert "stale_database_restore" in source
    # Old paths can be restored only in the pre-activation branch.
    assert "rolled_back_pre_activation" in source
