"""Only exact Root-pinned additive MCP may replace the old MCP peer.

All six original peer gates still apply. No image allowlist broadening.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from types import SimpleNamespace
import copy
import pytest

from tools import audit_journal_release_scope as scope

CANDIDATE="a"*40
OVERLAY="sha256:"+"c"*64
BASE=scope.BASE_IMAGES["jason-mcp-pilot"]


def root_addon(tmp_path,monkeypatch):
    p=tmp_path/"root-audit-owner-policy.json"
    policy={
       "schema_version":"1.0",
       "action":"ADOPT-EXACT-DAILY-AUDIT-JOURNAL",
       "candidate_sha":CANDIDATE,
       "rollback_sha":scope.ROLLBACK,
       "mcp_base_image_id":BASE,
       "mcp_overlay_image_id":OVERLAY,
       "one_use_executor":True,
       "global_freeze_unchanged":True,
       "standing_authority":False,
       "expires_at":(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat(),
    }
    p.write_bytes(json.dumps(policy,sort_keys=True).encode())
    p.chmod(0o600)
    monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",p)
    original=Path.lstat
    def root_custody(path,*args,**kwargs):
        m=original(path,*args,**kwargs)
        if path in (p,p.parent):
            return SimpleNamespace(st_mode=m.st_mode,st_uid=0,
                                   st_nlink=m.st_nlink,st_size=m.st_size)
        return m
    monkeypatch.setattr(Path,"lstat",root_custody)
    row={
       "Id":OVERLAY,
       "Config":{
          "User":"1000:1000",
          "Labels":{
            "com.teamaot.jason.audit_overlay_reviewed_main_sha":CANDIDATE,
            "com.teamaot.jason.audit_overlay_base_image_sha256":BASE[7:],
            "com.teamaot.jason.audit_overlay_purpose":"one-use-owner-archive-adoption",
          },
       }
    }
    def image_response(argv,**kwargs):
        assert argv==["/usr/bin/docker","image","inspect",OVERLAY]
        return SimpleNamespace(returncode=0,stdout=json.dumps([row]))
    monkeypatch.setattr(scope.subprocess,"run",image_response)
    return p,policy,row


def test_no_root_policy_retains_exact_original_images(tmp_path,monkeypatch):
    monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",
                        tmp_path/"no-Root-policy")
    assert scope.current_base_images(CANDIDATE)==scope.BASE_IMAGES


def test_only_root_attested_additive_mcp_image_accepted(tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    result=scope.current_base_images(CANDIDATE)
    assert result["jason-mcp-pilot"]==OVERLAY
    assert len(result)==len(scope.BASE_IMAGES)
    assert all(result[n]==v for n,v in scope.BASE_IMAGES.items()
               if n!="jason-mcp-pilot")
    facts={
        "dataset_identity":{"device":3,"inode":7},
        "producer_before":{},"producer_after":{},
        "archive_root_metadata":{"uid":1000,"gid":984,"mode":"0o2770"},
        "desired_after_sha256":"a"*64,
    }
    reviewed=scope.reviewed_scope(CANDIDATE,{}, {}, {},facts)
    assert reviewed["same_base_images"]["jason-mcp-pilot"]==OVERLAY
    assert reviewed["policy"]["candidate_sha"]==CANDIDATE


@pytest.mark.parametrize("field,value",[
    ("candidate_sha","0"*40),
    ("rollback_sha","0"*40),
    ("mcp_base_image_id","sha256:"+"f"*64),
    ("mcp_overlay_image_id","sha256:bad"),
    ("one_use_executor",False),
    ("global_freeze_unchanged",False),
    ("standing_authority",True),
    ("expires_at",(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()),
    ("action","generic-root-run"),
])
def test_changed_root_scope_or_expired_proof_denied(
        tmp_path,monkeypatch,field,value):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    policy[field]=value
    p.write_bytes(json.dumps(policy,sort_keys=True).encode())
    with pytest.raises(PermissionError,
                       match="AUDIT_OWNER_MCP_EXACT_PROVENANCE_DENIED"):
        scope.current_base_images(CANDIDATE)


@pytest.mark.parametrize("label,value",[
    ("com.teamaot.jason.audit_overlay_reviewed_main_sha","f"*40),
    ("com.teamaot.jason.audit_overlay_base_image_sha256","f"*64),
    ("com.teamaot.jason.audit_overlay_purpose","arbitrary-tools"),
])
def test_forged_addon_image_labels_fail(tmp_path,monkeypatch,label,value):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    row["Config"]["Labels"][label]=value
    with pytest.raises(PermissionError,
                       match="AUDIT_OWNER_MCP_EXACT_PROVENANCE_DENIED"):
        scope.current_base_images(CANDIDATE)


def test_invalid_addon_image_user_denied(tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    row["Config"]["User"]="0:0"
    with pytest.raises(PermissionError):
        scope.current_base_images(CANDIDATE)


def test_candidate_sha_drift_denied_even_for_current_root_image(
        tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    with pytest.raises(PermissionError):
        scope.current_base_images("f"*40)


def test_root_policy_wrong_mode_denied(tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    p.chmod(0o666)
    with pytest.raises(PermissionError):
        scope.current_base_images(CANDIDATE)


def test_symlinked_root_trust_rejected(tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    data=tmp_path/"trusted.json"
    p.rename(data)
    p.symlink_to(data)
    with pytest.raises(PermissionError):
        scope.current_base_images(CANDIDATE)


def test_live_peer_mismatch_fails_even_with_root_pin(tmp_path,monkeypatch):
    p,policy,row=root_addon(tmp_path,monkeypatch)
    original=scope.subprocess.run
    from test_audit_journal_protected_peers import peers
    live=peers()
    for role in live:
        if role["Name"]=="/jason-mcp-pilot":
            role["Image"]=OVERLAY
    def dispatch(argv,**kwargs):
        if argv[1:3]==["image","inspect"]:
            return original(argv,**kwargs)
        assert argv[:4]==["/usr/bin/docker","inspect","--type","container"]
        return SimpleNamespace(returncode=0,stdout=json.dumps(live))
    monkeypatch.setattr(scope.subprocess,"run",dispatch)
    result=scope.protected_peer_inventory()
    assert result["jason-mcp-pilot"]["image"]==OVERLAY
    live[0]["Image"]="sha256:"+"f"*64
    with pytest.raises(PermissionError):
        scope.protected_peer_inventory()


@pytest.mark.parametrize("stale", ["expired", "different_candidate"])
def test_original_live_mcp_does_not_require_unused_overlay_trust(tmp_path,monkeypatch,stale):
    p,policy,_=root_addon(tmp_path,monkeypatch)
    if stale=="expired":
        policy["expires_at"]=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
    else:
        policy["candidate_sha"]="0"*40
    p.write_bytes(json.dumps(policy,sort_keys=True).encode())
    from test_audit_journal_protected_peers import peers
    live=peers()
    def dispatch(argv,**kwargs):
        assert argv[:4]==["/usr/bin/docker","inspect","--type","container"]
        return SimpleNamespace(returncode=0,stdout=json.dumps(live))
    monkeypatch.setattr(scope.subprocess,"run",dispatch)
    verified=scope.protected_peer_inventory()
    assert verified["jason-mcp-pilot"]["image"]==BASE
    facts={"dataset_identity":{"device":3,"inode":7},
           "producer_before":{"jason-mcp-pilot":{"image":BASE}},
           "producer_after":{},"archive_root_metadata":{},
           "desired_after_sha256":"a"*64}
    assert scope.reviewed_scope(CANDIDATE,{}, {}, {},facts)["same_base_images"]==scope.BASE_IMAGES


def test_expired_overlay_still_denies_an_actual_overlay_peer(tmp_path,monkeypatch):
    p,policy,_=root_addon(tmp_path,monkeypatch)
    policy["expires_at"]=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
    p.write_bytes(json.dumps(policy).encode())
    from test_audit_journal_protected_peers import peers
    live=peers()
    for row in live:
        if row["Name"]=="/jason-mcp-pilot":row["Image"]=OVERLAY
    def dispatch(argv,**kwargs):
        assert argv[:4]==["/usr/bin/docker","inspect","--type","container"]
        return SimpleNamespace(returncode=0,stdout=json.dumps(live))
    monkeypatch.setattr(scope.subprocess,"run",dispatch)
    with pytest.raises(PermissionError,match="AUDIT_OWNER_MCP_EXACT_PROVENANCE_DENIED"):
        scope.protected_peer_inventory()


def test_unknown_live_mcp_still_denied_without_overlay_trust(tmp_path,monkeypatch):
    monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",tmp_path/"absent-policy")
    from test_audit_journal_protected_peers import peers
    live=peers()
    for row in live:
        if row["Name"]=="/jason-mcp-pilot":row["Image"]="sha256:"+"f"*64
    monkeypatch.setattr(scope.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(live)))
    with pytest.raises(PermissionError,match="AUDIT_PEER_IDENTITY_UNTRUSTED"):
        scope.protected_peer_inventory()
