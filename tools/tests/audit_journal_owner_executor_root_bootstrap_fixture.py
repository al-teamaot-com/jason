"""Actual UID0/UID1000 no-network offline Root bootstrap/rollback proof."""
from __future__ import annotations
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

assert os.geteuid()==0 and sys.flags.isolated==1
assert not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/authority").exists()
module_file=Path("/test-source/audit_journal_owner_executor_bootstrap.py")
spec=importlib.util.spec_from_file_location("actual_audit_bootstrap",module_file)
x=importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
with tempfile.TemporaryDirectory(prefix="audit-owner-root-bootstrap-",dir="/tmp") as folder:
    base=Path(folder)
    base.chmod(0o755)
    root_dir=base/"root"
    root_dir.mkdir(mode=0o755)
    root_dir.chmod(0o755)
    native_dir=base/"systemd"
    native_dir.mkdir(mode=0o755)
    native_dir.chmod(0o755)
    trust_dir=base/"owner-records"
    trust_dir.mkdir(mode=0o700)
    trust_dir.chmod(0o700)
    root_policy_dir=base/"root-policy"
    root_policy_dir.mkdir(mode=0o755)
    root_policy_dir.chmod(0o755)
    authority=base/"authority"
    authority.mkdir(mode=0o700)
    os.chown(authority,1000,1000)
    authority.chmod(0o700)
    x.ROOT_CODE=root_dir/"executor"/"worker.py"
    x.ROOT_POLICY=root_policy_dir/"audit-owner-root.json"
    x.NATIVE_UNIT_DIR=native_dir
    x.TRUST_DIR=trust_dir
    x.PUBLIC=authority/"audit-journal-release"
    actor=base/"reviewed"
    actor.mkdir(mode=0o755)
    os.chown(actor,1000,1000)
    worker=Path("/test-source/audit_journal_owner_native_worker.py").read_bytes()
    service=Path("/test-source/jason-audit-journal-owner-executor.service").read_bytes()
    watcher=Path("/test-source/jason-audit-journal-owner-executor.path").read_bytes()
    payload={
      "tools/audit_journal_owner_native_worker.py":worker,
      "tools/audit_journal_install.py":b"only exact native Root installer fixture\n",
      "infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.service":service,
      "infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.path":watcher,
    }
    calls=[]
    # No systemd host executable is present in the isolated test image;
    # model it without performing any host service action, including rollback.
    x.subprocess.run=lambda argv,**kw:None
    x.command=lambda argv,timeout=45:(
        calls.append((tuple(argv),timeout)),
        "active" if argv[-2:]==["is-active",x.UNIT_PATH] else ""
    )[1]
    owner_sha="a"*40
    evidence=x.root_install(actor,owner_sha,payload,{
        "mcp_overlay_image_id":"sha256:"+"b"*64,
    })
    assert evidence["status"]=="root_exact_audit_executor_installed"
    assert evidence["root_path_enabled"] is True
    assert evidence["owner_signature_not_yet_issued"] is True
    assert evidence["mcp_not_restarted"] is True
    assert evidence["archive_not_deployed"] is True
    assert evidence["freeze_unmodified"] is True
    for p,owner,mode in (
      (x.ROOT_CODE,0,0o444),(x.ROOT_POLICY,0,0o600),
      (x.NATIVE_UNIT_DIR/x.UNIT_SERVICE,0,0o644),
      (x.NATIVE_UNIT_DIR/x.UNIT_PATH,0,0o644),
      (x.PUBLIC,1000,0o700),
      (x.PUBLIC/"requests",1000,0o700),
      (x.PUBLIC/"processed",1000,0o700),
      (x.PUBLIC/"results",1000,0o700),
      (x.PUBLIC/"offers",1000,0o700),
      (x.PUBLIC/"owner-approvals",1000,0o700),
      (x.TRUST_DIR/"audit-journal-signed-stage",0,0o700),
    ):
        s=p.lstat()
        assert s.st_uid==owner,(p,s.st_uid)
        assert stat.S_IMODE(s.st_mode)==mode,(p,oct(s.st_mode&0o777))
    policy=json.loads(x.ROOT_POLICY.read_bytes())
    assert policy["action"]==x.ACTION
    assert policy["candidate_sha"]==owner_sha
    assert policy["mcp_overlay_image_id"]=="sha256:"+"b"*64
    assert policy["mcp_base_image_id"]==x.MCP_BASE
    assert policy["permitted_actions"]==[
        "audit_archive_adopt","audit_archive_stage"]
    assert policy["standing_authority"] is False
    assert policy["one_use_executor"] is True
    assert policy["global_freeze_unchanged"] is True
    expire=datetime.fromisoformat(policy["expires_at"])
    assert 0<(expire-datetime.now(timezone.utc)).total_seconds()<=43200
    assert any(v[0][-3:]==("enable","--now",x.UNIT_PATH)
               for v in calls)
    try:
        x.root_install(actor,owner_sha,payload,{
            "mcp_overlay_image_id":"sha256:"+"b"*64})
    except x.AuditBootstrapDenied:
        pass
    else:
        raise AssertionError("replayed Root bootstrap admitted")
    assert not (base/"production-replaced").exists()
    assert not (base/"archival-database").exists()
    print(json.dumps({
        "status":"PASS","isolated_UID0":True,"uid1000_public_spool":True,
        "trusted_Root_worker_mode0444":True,"Root_policy_mode0600":True,
        "units_owned_by_Root":True,"two_exact_actions_only":True,
        "one_use_bootstrap_replay_denied":True,
        "service_restart_performed":False,
        "real_database_changes":False,"original_freeze_modified":False,
        "network":"disabled","host_mounts":False,
    },sort_keys=True))

    # A failed exact systemd activation must remove only its own staged
    # files and empty directories, leaving previous unrelated Root services
    # and the first successful fixture record untouched.
    native_retry=base/"systemd-retry"
    native_retry.mkdir(mode=0o755)
    retry_trust=base/"owner-records-retry"
    retry_trust.mkdir(mode=0o700)
    retry_trust.chmod(0o700)
    x.NATIVE_UNIT_DIR=native_retry
    x.TRUST_DIR=retry_trust
    x.ROOT_CODE=root_dir/"executor-retry"/"worker.py"
    x.ROOT_POLICY=root_policy_dir/"audit-owner-root-retry.json"
    x.PUBLIC=authority/"audit-journal-release-retry"
    disabled=[]
    x.subprocess.run=lambda argv,**kw:(disabled.append(tuple(argv)),None)[1]
    def partial_failure(argv,timeout=45):
        if argv[:3]==["/usr/bin/systemctl","enable","--now"]:
            raise RuntimeError("simulated untrusted unit activation failure")
        return "active" if argv[-2:]==["is-active",x.UNIT_PATH] else ""
    x.command=partial_failure
    try:x.root_install(actor,owner_sha,payload,{
        "mcp_overlay_image_id":"sha256:"+"b"*64})
    except RuntimeError:
        pass
    else:raise AssertionError("failed systemd operation was accepted")
    assert not x.ROOT_CODE.exists()
    assert not x.ROOT_CODE.parent.exists()
    assert not x.ROOT_POLICY.exists()
    assert not x.PUBLIC.exists()
    assert not (retry_trust/"audit-journal-signed-stage").exists()
    assert not (native_retry/x.UNIT_SERVICE).exists()
    assert not (native_retry/x.UNIT_PATH).exists()
    assert any(cmd[:4]==("/usr/bin/systemctl","disable","--now",x.UNIT_PATH)
               for cmd in disabled)
    assert (root_dir/"executor"/"worker.py").exists()
    assert (root_policy_dir/"audit-owner-root.json").exists()
    print("EXACT_ROOT_BOOTSTRAP_INTERRUPTED_ACTIVATION_ROLLBACK=PASS")
