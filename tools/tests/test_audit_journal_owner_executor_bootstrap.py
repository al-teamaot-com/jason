"""Exact audit-only Root bootstrap: no production work from staging.

The real UID0/no-host-mount Root fixture separately covers ownership.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from types import SimpleNamespace
import os
import pytest

from tools import audit_journal_owner_executor_bootstrap as x

CANDIDATE="a"*40
OVERLAY="sha256:"+"e"*64


def prepared_source(tmp_path,monkeypatch):
    source=tmp_path/"audit-owner-main-fixture"
    source.mkdir(mode=0o755)
    source.chmod(0o755)
    # Synthetic hosted-runner source files are owned by the runner (often UID
    # 1001), not Jason's real UID1000. Change only fixture metadata readback;
    # Root production source_verified still requires literal UID1000.
    actual_lstat=Path.lstat
    def synthetic_ownership(path,*args,**kwargs):
        info=actual_lstat(path,*args,**kwargs)
        if path==source or path.is_relative_to(source):
            return SimpleNamespace(st_uid=1000,st_mode=info.st_mode,
                                   st_nlink=info.st_nlink,st_size=info.st_size)
        return info
    monkeypatch.setattr(Path,"lstat",synthetic_ownership)
    monkeypatch.setattr(x,"SOURCE_PREFIX",tmp_path)
    expected={}
    for index,name in enumerate(x.SOURCE):
        file=source/name
        file.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        body=("reviewed native source "+name+"\n").encode()
        file.write_bytes(body)
        file.chmod(0o644)
        expected[name]=body
    def git(cwd,*args):
        assert cwd==source
        return { "rev-parse":CANDIDATE, "status":"",
                 "ls-remote":CANDIDATE+"\trefs/heads/main"}[args[0]]
    monkeypatch.setattr(x,"al_git",git)
    def git_file(args,**kwargs):
        assert args[-2]=="show"
        revision,name=args[-1].split(":",1)
        assert revision==CANDIDATE
        return expected[name]
    monkeypatch.setattr(x.subprocess,"check_output",git_file)
    return source,expected


def prepared_live(tmp_path,monkeypatch,payload):
    root=tmp_path/"live"
    root.mkdir(mode=0o755)
    def record(name,value):
        p=root/name;p.write_bytes(json.dumps(value).encode())
        return p
    monkeypatch.setattr(x,"CONTROL_READBACK",record("control.json",{
        "circuit_breaker":{"state":"closed",
            "revalidated_revision":x.ROLLBACK_SHA}}))
    drift={
        "status":"pass","problems":[],
        "observed_at":datetime.now(timezone.utc).isoformat()
    }
    monkeypatch.setattr(x,"DRIFT_READBACK",record("drift.json",drift))
    monkeypatch.setattr(x,"FAST_READBACK",record(
        "fast.json",{"status":"pass","failures":[]}))
    monkeypatch.setattr(x,"FULL_READBACK",record(
        "full.json",{"status":"pass","failures":[]}))
    frozen={
       "schema_version":"1.0","status":"active",
       "scope":"manual-and-automatic-production-promotions",
       "release_exception":"none approved",
    }
    freeze=record("freeze.json",frozen)
    freeze.chmod(0o600)
    actual_lstat=Path.lstat
    def synthetic_freeze_ownership(path,*args,**kwargs):
        info=actual_lstat(path,*args,**kwargs)
        if path==freeze:
            return SimpleNamespace(st_uid=1000,st_mode=info.st_mode,
                                   st_nlink=info.st_nlink,st_size=info.st_size)
        return info
    monkeypatch.setattr(Path,"lstat",synthetic_freeze_ownership)
    monkeypatch.setattr(x,"FREEZE_PATH",freeze)
    journal=root/"orchestration-events.sqlite3"
    journal.write_bytes(b"fixture-sqlite")
    monkeypatch.setattr(x,"CANONICAL_DB",journal)
    archive=root/"archive"
    archive.mkdir()
    monkeypatch.setattr(x,"ARCHIVE_DRIVE",archive)
    old_mount=Path.is_mount
    old_stat=Path.stat
    monkeypatch.setattr(Path,"is_mount",lambda p:p==archive or old_mount(p))
    # Pure unit fixtures share a temporary real filesystem. Only the fixture
    # sees a different synthetic archive st_dev; actual host Root still checks
    # real os.stat() plus os.path.ismount() against the independent disk.
    def synthetic_device(p,*args,**kwargs):
        real=old_stat(p,*args,**kwargs)
        if p==archive:
            return SimpleNamespace(st_dev=real.st_dev+1)
        return real
    monkeypatch.setattr(Path,"stat",synthetic_device)
    monkeypatch.setattr(x.shutil,"disk_usage",
                        lambda p:SimpleNamespace(free=1024**4))
    monkeypatch.setattr(x,"ROOT_CODE",root/"root"/"worker.py")
    monkeypatch.setattr(x,"ROOT_POLICY",root/"policy.json")
    monkeypatch.setattr(x,"NATIVE_UNIT_DIR",root)
    monkeypatch.setattr(x,"PUBLIC",root/"public")
    monkeypatch.setattr(x,"TRUST_DIR",root/"owner-release")
    calls=[]
    probe={"mcp_overlay":x.digest(payload[
             "infrastructure/jason-audit-journal-owner-executor/mcp_overlay.py"]),
           "owner_approval":x.digest(payload[
             "implementation/mcp_service/src/jason_mcp/audit_journal_adoption_approval.py"])}
    def command(argv,timeout=45):
        calls.append((argv,timeout))
        if argv[:3]==["/usr/bin/docker","inspect","jason-mcp-pilot"]:
            return json.dumps([{"Image":x.MCP_BASE,"State":{"Running":True}}])
        if argv[:3]==["/usr/bin/docker","image","inspect"]:
            original={"User":"1000:1000","Cmd":["jason-mcp"],
                      "Entrypoint":None,"WorkingDir":"/opt/jason-src",
                      "Env":["A=fixture"]}
            if argv[-1]==x.MCP_BASE:
                return json.dumps([{"Id":x.MCP_BASE,"Config":original,
                                    "RootFS":{"Layers":["base1","base2"]}}])
            return json.dumps([{"Id":OVERLAY,
                "RootFS":{"Layers":["base1","base2","added1","added2","added3"]},
                "Config":{
                "User":"1000:1000","Cmd":["python","/opt/jason-src/mcp_overlay.py"],
                "Entrypoint":None,"WorkingDir":"/opt/jason-src",
                "Env":["A=fixture"],
                "Labels":{
                  "com.teamaot.jason.audit_overlay_reviewed_main_sha":CANDIDATE,
                  "com.teamaot.jason.audit_overlay_base_image_sha256":x.MCP_BASE[7:],
                  "com.teamaot.jason.audit_overlay_purpose":
                      "one-use-owner-archive-adoption",
                }}}])
        if argv[:2]==["/usr/bin/docker","run"]:
            assert "--network=none" in argv
            assert "--cap-drop=ALL" in argv
            assert "--security-opt=no-new-privileges" in argv
            assert "--read-only" in argv
            assert "--mount" not in argv
            return json.dumps(probe)
        raise AssertionError("unexpected privileged command")
    monkeypatch.setattr(x,"command",command)
    return root,drift,probe,calls


def test_verified_main_checkout_is_readonly_and_exact(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    assert x.source_verified(source,CANDIDATE)==rows
    changed=source/x.SOURCE[1]
    changed.write_bytes(b"unreviewed")
    with pytest.raises(x.AuditBootstrapDenied,
                       match="PROTECTED_MAIN_SOURCE_DRIFT"):
        x.source_verified(source,CANDIDATE)
    assert not any((tmp_path/"live").glob("**/*"))


def test_wrong_source_revision_or_alias_denied(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    with pytest.raises(x.AuditBootstrapDenied):
        x.source_verified(source,"0"*40)
    renamed=tmp_path/"arbitrary-checkout"
    source.rename(renamed)
    with pytest.raises(x.AuditBootstrapDenied):
        x.source_verified(renamed,CANDIDATE)


def test_approved_readonly_root_preflight_pins_exact_live_image(
        tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    result=x.live_readonly_admission(source,CANDIDATE,rows)
    assert result["mcp_overlay_image_id"]==OVERLAY
    assert result["original_mcp_image_id"]==x.MCP_BASE
    assert result["original_freeze_sha256"]
    assert result["archive_only"] is True
    assert result["freeze_left_active"] is True
    assert len([v for v in calls if v[0][:2]==["/usr/bin/docker","run"]])==1
    assert not (root/"root").exists()
    assert not (root/"policy.json").exists()


def test_forged_additive_code_never_passes_root_preflight(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    probe["mcp_overlay"]="0"*64
    with pytest.raises(x.AuditBootstrapDenied,
                       match="EXACT_MCP_ADDITIVE_CODE_DIGEST_MISMATCH"):
        x.live_readonly_admission(source,CANDIDATE,rows)


def test_stale_drift_refuses_even_when_original_report_passed(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    drift["observed_at"]=(datetime.now(timezone.utc)-
                          timedelta(minutes=7)).isoformat()
    x.DRIFT_READBACK.write_bytes(json.dumps(drift).encode())
    with pytest.raises(x.AuditBootstrapDenied,
                       match="PRODUCTION_DRIFT_NOT_FRESH_PASS"):
        x.live_readonly_admission(source,CANDIDATE,rows)


def test_breaker_open_refused(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    x.CONTROL_READBACK.write_bytes(json.dumps({
        "circuit_breaker":{"state":"open",
            "revalidated_revision":x.ROLLBACK_SHA}}).encode())
    with pytest.raises(x.AuditBootstrapDenied,
                       match="PROTECTED_BREAKER_NOT_VERIFIED"):
        x.live_readonly_admission(source,CANDIDATE,rows)


def test_changed_production_freeze_refused(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    x.FREEZE_PATH.write_bytes(json.dumps({
       "status":"removed","scope":"manual-and-automatic-production-promotions",
       "release_exception":"none approved"}).encode())
    with pytest.raises(x.AuditBootstrapDenied,
                       match="GLOBAL_FREEZE_MUST_REMAIN_UNCHANGED"):
        x.live_readonly_admission(source,CANDIDATE,rows)


def test_mcp_image_change_before_signed_root_bootstrap_denied(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    original=x.command
    def swapped(argv,timeout=45):
        result=original(argv,timeout)
        if argv[:3]==["/usr/bin/docker","inspect","jason-mcp-pilot"]:
            return json.dumps([{"Image":OVERLAY,"State":{"Running":True}}])
        return result
    monkeypatch.setattr(x,"command",swapped)
    with pytest.raises(x.AuditBootstrapDenied,
                       match="MCP_LKG_IMAGE_NOT_RUNNING"):
        x.live_readonly_admission(source,CANDIDATE,rows)


def test_bootstrap_requires_real_root_and_exact_per_run_intent(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    with pytest.raises(x.AuditBootstrapDenied,
                       match="EXACT_HOST_ROOT_REQUIRED"):
        x.root_install(source,CANDIDATE,rows,{})
    assert not (tmp_path/"root").exists()
    assert "sudo" not in Path(x.__file__).read_text()


def test_changed_base_layer_lineage_is_denied_even_with_forged_labels(tmp_path,monkeypatch):
    source,rows=prepared_source(tmp_path,monkeypatch)
    root,drift,probe,calls=prepared_live(tmp_path,monkeypatch,rows)
    original=x.command
    def forged(argv,timeout=45):
        if argv[:3]==["/usr/bin/docker","image","inspect"] and argv[-1]!=x.MCP_BASE:
            row=json.loads(original(argv,timeout))[0]
            row["RootFS"]["Layers"][0]="forged_base_layer"
            return json.dumps([row])
        return original(argv,timeout)
    monkeypatch.setattr(x,"command",forged)
    with pytest.raises(x.AuditBootstrapDenied,
                       match="MCP_ADDITIVE_IMAGE_EXACT_BASE_ANCESTRY_DENIED"):
        x.live_readonly_admission(source,CANDIDATE,rows)
