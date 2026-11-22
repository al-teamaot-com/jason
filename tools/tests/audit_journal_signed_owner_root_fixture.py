"""Actual UID0 no-network/no-host-mount Root/UID1000 offer custody fixture."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import json
import os
import stat
import sys
import tempfile

def load(path):
    spec=importlib.util.spec_from_file_location("audit_journal_root_owner_fixture",str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

source=Path("/usr/local/lib/jason/audit-journal/trusted/tools/audit_journal_signed_owner_bridge.py")
bridge=load(source)
assert os.geteuid()==0 and sys.flags.isolated==1
assert not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/authority").exists()
with tempfile.TemporaryDirectory(prefix="audit-signed-owner-root-",dir="/tmp") as td:
    base=Path(td);base.chmod(0o755)
    pub=base/"authority";pub.mkdir(mode=0o700)
    os.chown(pub,1000,1000)
    public=pub/"audit-journal-release"
    private=base/"owner-root";private.mkdir(mode=0o700)
    freeze=base/"freeze"
    freeze.write_text(json.dumps({
       "reason":"legacy owner freeze preserved",
       "release_exception":"none approved",
       "remove_only_after":"new explicit exact-SHA owner unfreeze decision",
       "schema_version":"1.0",
       "scope":"manual-and-automatic-production-promotions",
       "status":"active",
    },sort_keys=True))
    os.chown(freeze,1000,1000);freeze.chmod(0o600)
    bridge.PUBLIC=public
    bridge.STAGED=private/"signed-stage"
    bridge.FREEZE=freeze
    candidate="a"*40
    scope={"action":bridge.ACTION,"policy":{
        "candidate_sha":candidate,"rollback_sha":bridge.ROLLBACK},
        "dataset_identity":{"device":13,"inode":173},
        "protected_peers":{"jason-runtime":"healthy"}}
    gate={"breaker":"closed","drift":"pass",
          "peers_verified":True,"mount_verified":True,
          "dataset_identity":{"device":13,"inode":173}}
    before_freeze=freeze.read_bytes()
    offer=bridge.create_staged_offer(scope,candidate,gate)
    assert freeze.read_bytes()==before_freeze
    assert offer["release_id"]=="release-"+candidate[:16]
    assert offer["root_stage_receipt_sha256"]
    stage=bridge.STAGED/(offer["release_id"]+".json")
    public_offer=public/"offers"/(offer["release_id"]+".json")
    for p,uid,mode in (
        (stage,0,0o400),(public_offer,1000,0o600),
        (bridge.STAGED,0,0o700),(public/"offers",1000,0o700),
        (public/"owner-approvals",1000,0o700)):
        info=p.lstat()
        assert info.st_uid==uid, (p,info.st_uid)
        assert stat.S_IMODE(info.st_mode)==mode, (p,oct(info.st_mode))
    assert bridge.private_json(stage,0,0o400)["scope"]==scope
    assert bridge.private_json(public_offer,1000,0o600)["root_stage_receipt_sha256"]==bridge.digest(bridge.canon(
        bridge.private_json(stage,0,0o400)))
    try:bridge.create_staged_offer(scope,candidate,gate)
    except bridge.ArchiveOwnerDenied:pass
    else:raise AssertionError("staged owner offer replay accepted")
    # This minimal Root image intentionally has no cryptography package.
    # Its scope here is real UID0/UID1000 filesystem custody and missing
    # signature denial. The host test suite uses real Ed25519 verification.
    import types
    kernel=types.ModuleType("kernel")
    signed=types.ModuleType("kernel.signed_owner_release")
    signed.read_pinned_root_owner_public_key=lambda path: None
    signed.verify_exact_owner_release=lambda *args,**kwargs: (_ for _ in ()).throw(
        AssertionError("missing signed Owner record must deny before signature"))
    sys.modules["kernel"]=kernel
    sys.modules["kernel.signed_owner_release"]=signed
    try:bridge.verify_previously_signed_root_offer(scope,candidate,gate)
    except (FileNotFoundError,bridge.ArchiveOwnerDenied):pass
    else:raise AssertionError("missing signed Owner approval accepted")
    proof={"candidate_sha":candidate,"owner_oid":bridge.OWNER,
           "same_scope_recheck_passed":True,"standalone_archive_only":True,
           "new_global_unfreeze":False,"approval_id":"owner-mcp-"+"a"*32}
    consumed=bridge.consume_one_use(candidate,proof)
    assert consumed.stat().st_uid==0
    assert stat.S_IMODE(consumed.stat().st_mode)==0o400
    try:bridge.consume_one_use(candidate,proof)
    except bridge.ArchiveOwnerDenied:pass
    else:raise AssertionError("one-use Root approval replay accepted")
    assert not (base/"audit-install").exists()
    assert freeze.read_bytes()==before_freeze
    print(json.dumps({
      "result":"PASS","root_identity":True,"network":"none",
      "host_mounts":False,"root_stage_mode":"0400",
      "public_offer_uid":1000,"public_offer_mode":"0600",
      "immutable_original_global_freeze":True,
      "missing_signed_Owner_denied":True,
      "owner_consumption_one_use":True,
      "migrated_database":False,"new_root_service":False,
      "provider_writes":False,
    },sort_keys=True))
