"""Disposable filesystem and fake-systemctl acceptance of one-Owner host repair.

All service calls are captured locally; no root host, provider, service, database
or production circuit-breaker modification is permitted during these tests.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
import subprocess

import pytest

from tools import pmv4_c_host_recovery_root as root


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    src=tmp_path/"artifact"
    adapter=tmp_path/"root-lib"/"pmv4-c-canonical-health-v1"/"pmv4_c_authority_health_adapter.py"
    units=tmp_path/"systemd"
    state=tmp_path/"root-control"
    (src/"src"/"tools").mkdir(parents=True)
    (src/"src"/"tools"/"pmv4_c_authority_health_adapter.py").write_text("safe = True\n")
    (src/"dropins").mkdir(parents=True)
    units.mkdir()
    state.mkdir(mode=0o700)
    for unit in (*root.UNITS,*root.EXPORTERS):
        (src/"dropins"/(unit+".conf")).write_text(
            "[Service]\nEnvironment=ONE_EXACT_CANONICAL_FILE=1\n"
        )
    monkeypatch.setattr(root,"ARTIFACT",src)
    monkeypatch.setattr(root,"ADAPTER",adapter)
    monkeypatch.setattr(root,"ROOT_STATE",state)
    monkeypatch.setattr(root,"UNIT_ROOT",units)
    plan={
        "candidate_sha":"a"*40,"scope_sha256":"b"*64,
        "source_hashes":{"tools/pmv4_c_authority_health_adapter.py":"c"*64}
    }
    monkeypatch.setattr(root,"preflight",lambda path:plan)
    monkeypatch.setattr(root,"verify_owner",lambda plan:{"approval_id":"owner-mcp-"+"d"*32})
    monkeypatch.setattr(root,"previous_stage_c",lambda plan:None)
    monkeypatch.setattr(root,"active_state",lambda plan:None)
    monkeypatch.setattr(root,"root_source",lambda plan:None)
    @contextmanager
    def exclusive():
        yield
    monkeypatch.setattr(root,"locked_host",exclusive)
    calls=[]
    def fake_command(*argv,timeout=30,check=True):
        calls.append(argv)
        if argv[:2]==("/usr/bin/systemctl","is-active"):
            if argv[2]==root.UNITS[1]:
                return subprocess.CompletedProcess(argv,3,"inactive\n","")
            return subprocess.CompletedProcess(argv,0,"active\n","")
        return subprocess.CompletedProcess(argv,0,"","")
    monkeypatch.setattr(root,"run",fake_command)
    # Privileged chown/install semantics are independently source-enforced.
    # In this nonroot disposable fixture, preserve overwrite/mode behavior
    # while replacing ONLY host ownership operations with synthetic ownership.
    monkeypatch.setattr(root.os,"chown",lambda *_args,**_kwargs:None)
    original_install=root.install_bytes
    def test_only_install(path,data):
        if path.exists() or path.is_symlink():
            raise root.HostRecoveryDenied("HOST_RECOVERY_INSTALL_COLLISION:"+path.name)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.parent.chmod(0o755)  # simulated exact root-owned systemd unit directory
        parent=path.parent.lstat()
        assert not path.parent.is_symlink() and parent.st_uid==os.getuid()
        assert not (parent.st_mode & 0o022)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
        with os.fdopen(fd,"wb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        path.chmod(0o444)
        assert path.read_bytes()==data
    monkeypatch.setattr(root,"install_bytes",test_only_install)
    return src,adapter,units,state,plan,calls


def read_root_journal(state,plan):
    p=state/("host-recovery-"+plan["candidate_sha"][:12]+".jsonl")
    raw=p.read_bytes().splitlines()
    previous="0"*64
    for index,line in enumerate(raw):
        item=json.loads(line)
        signature=item.pop("hash")
        assert item["index"]==index
        assert item["previous_sha256"]==previous
        assert signature==root.sha(root.canon(item))
        previous=signature
    return [json.loads(x) for x in raw]


def test_success_stages_exact_units_and_real_full_proof_not_pass(
    sandbox,tmp_path,capsys,
):
    src,adapter,units,state,plan,calls=sandbox
    root.execute(src/"root-release-plan.json")
    stdout=capsys.readouterr().out
    assert "HOST_RECOVERY_EXACT_INSTALL=VERIFIED" in stdout
    assert "FULL_INTEGRITY=STARTED_NOT_YET_VERIFIED" in stdout
    assert "PRODUCTION_BREAKER_RESET=false" in stdout
    assert adapter.read_text()=="safe = True\n"
    assert adapter.stat().st_mode & 0o111
    expected={str(units/(u+".d")/(
        root.HEALTH_DROPIN if u in root.UNITS else root.DROPIN_NAME))
        for u in (*root.UNITS,*root.EXPORTERS)}
    assert {str(p) for p in units.rglob("*.conf")}==expected
    assert sum(c[:2]==("/usr/bin/systemctl","restart") for c in calls)==5
    assert ("/usr/bin/systemctl","start","--no-block",root.UNITS[1]) in calls
    assert all("reset-failed" not in c for c in calls)
    assert all("jason-runtime" not in c and "jason-mcp-pilot" not in c
               for c in calls)
    events=[x["event"] for x in read_root_journal(state,plan)]
    assert events==[
        "begin","reviewed_units_installed","exporters_restarted",
        "full_proof_started_pending"
    ]


def test_failed_second_exporter_rolls_back_exact_new_units_and_adapter(
    sandbox,monkeypatch,
):
    src,adapter,units,state,plan,calls=sandbox
    original=root.run
    count=[0]
    def fail_one(*args,**kwargs):
        if args[:2]==("/usr/bin/systemctl","restart"):
            count[0]+=1
            if count[0]==2:
                raise root.HostRecoveryDenied("SIMULATED_EXACT_EXPORTER_FAILURE")
        return original(*args,**kwargs)
    monkeypatch.setattr(root,"run",fail_one)
    with pytest.raises(root.HostRecoveryDenied,match="SIMULATED_EXACT_EXPORTER_FAILURE"):
        root.execute(src/"root-release-plan.json")
    assert not adapter.exists()
    assert not list(units.rglob("*.conf"))
    assert all("reset-failed" not in cmd for cmd in calls)
    assert ("/usr/bin/systemctl","start","--no-block",root.UNITS[1]) not in calls
    events=[x["event"] for x in read_root_journal(state,plan)]
    assert events[-1]=="pre_integrity_rollback_attempted"


def test_reentry_refuses_consumed_root_audit(sandbox):
    src,adapter,units,state,plan,calls=sandbox
    root.execute(src/"root-release-plan.json")
    with pytest.raises(root.HostRecoveryDenied,match="ALREADY_CONSUMED"):
        root.execute(src/"root-release-plan.json")


def test_foreign_path_install_never_overwrites_existing_file(sandbox):
    src,adapter,units,state,plan,calls=sandbox
    foreign=units/"existing.conf"
    foreign.write_bytes(b"KEEP_ORIGINAL")
    with pytest.raises(root.HostRecoveryDenied,match="INSTALL_COLLISION"):
        root.install_bytes(foreign,b"NEW")
    assert foreign.read_bytes()==b"KEEP_ORIGINAL"
