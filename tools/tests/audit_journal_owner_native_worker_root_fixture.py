"""Isolated UID0/UID1000 exact Root-worker provenance, request and replay."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from hashlib import sha256
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

with tempfile.TemporaryDirectory(prefix="audit-root-executor-fixture-",dir="/tmp") as d:
    base=Path(d);base.chmod(0o755)
    installed=base/"installed"
    installed.mkdir(mode=0o755)
    worker=installed/"worker.py"
    worker.write_bytes(Path("/test-source/worker.py").read_bytes())
    worker.chmod(0o444)
    spec=importlib.util.spec_from_file_location("reviewed_audit_worker",str(worker))
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
    x.INSTALLED=worker
    x.TRUST=base/"trust.json"
    x.WORKTREE_PREFIX=str(base/"audit-owner-main-")
    checkout=base/"audit-owner-main-synthetic"
    checkout.mkdir(mode=0o755)
    os.chown(checkout,1000,1000)
    checkout.chmod(0o755)
    sha="a"*40
    policy={
       "schema_version":"1.0","action":x.ACTION,
       "candidate_sha":sha,"rollback_sha":x.ROLLBACK,
       "worker_sha256":sha256(worker.read_bytes()).hexdigest(),
       "installer_sha256":"b"*64,
       "mcp_base_image_id":"sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477",
       "mcp_overlay_image_id":"sha256:"+"a"*64,
       "source_worktree":str(checkout),
       "standing_authority":False,"one_use_executor":True,
       "permitted_actions":sorted(x.ALLOWED),
       "expires_at":(datetime.now(timezone.utc)+
                     timedelta(hours=12)).isoformat(),
       "licensed_owner_oid":"bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
       "global_freeze_unchanged":True,
    }
    x.TRUST.write_bytes(x.canonical(policy))
    x.TRUST.chmod(0o600)
    confirmed,repo=x.root_stage_trust()
    assert confirmed==policy and repo==checkout
    policy_bad=dict(policy,installer_sha256="bad")
    x.TRUST.chmod(0o600);x.TRUST.write_bytes(x.canonical(policy_bad))
    try:x.root_stage_trust()
    except x.NativeArchiveDenied:pass
    else:raise AssertionError("forged Root installer digest accepted")
    x.TRUST.write_bytes(x.canonical(policy))
    authority=base/"public";authority.mkdir(mode=0o700)
    os.chown(authority,1000,1000)
    authority.chmod(0o700)
    x.AUTH=authority
    for part in ("requests","processed","results"):
        f=authority/part;f.mkdir(mode=0o700);os.chown(f,1000,1000)
        f.chmod(0o700)
    x.REQUESTS=authority/"requests"
    x.PROCESSED=authority/"processed"
    x.RESULTS=authority/"results"
    x.request_folders()
    request={
      "schema_version":"1.0","request_id":"c"*32,
      "candidate_sha":sha,"release_id":"release-"+sha[:16],
      "action":"audit_archive_stage",
    }
    req=x.REQUESTS/(request["request_id"]+".json")
    req.write_bytes(x.canonical(request));req.chmod(0o600)
    os.chown(req,1000,1000)
    assert x.checked_request(req,policy)==request
    request["action"]="arbitrary_root_shell"
    req.write_bytes(x.canonical(request))
    try:x.checked_request(req,policy)
    except x.NativeArchiveDenied:pass
    else:raise AssertionError("unapproved Root action accepted")
    request["action"]="audit_archive_stage"
    req.write_bytes(x.canonical(request))
    os.chmod(req,0o666)
    try:x.checked_request(req,policy)
    except x.NativeArchiveDenied:pass
    else:raise AssertionError("world-writable Root request accepted")
    os.chmod(req,0o600)
    result=x.RESULTS/("c"*32+".json")
    x.exclusive_result(result,{
       "schema_version":"1.0","request_id":"c"*32,
       "status":"root_exact_owner_offer_staged",
       "production_deployment":False,
    })
    st=result.lstat()
    assert st.st_uid==1000 and stat.S_IMODE(st.st_mode)==0o600
    try:x.exclusive_result(result,{"request_id":"c"*32})
    except x.NativeArchiveDenied:pass
    else:raise AssertionError("Root result replay accepted")
    assert not (base/"production").exists()
    assert not (base/"archive").exists()
    print(json.dumps({
       "status":"PASS","UID0":True,"network":"disabled",
       "host_bind_mounts":False,
       "worker_root_custody_0444":True,
       "signed_exact_root_policy_0600":True,
       "source_sha_and_installer_digest_pinned":True,
       "uid1000_request_and_result_0600":True,
       "arbitrary_root_command_denied":True,
       "one_use_result_replay_denied":True,
       "archive_mutation":False,"production_mutation":False,
    },sort_keys=True))
