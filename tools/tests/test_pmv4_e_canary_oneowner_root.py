"""Source-only root transaction gates, original Owner proof, exact policy rollback."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from tools import pmv4_e_canary_oneowner_root as root
from tools import pmv4_e_canary_drift_policy as drift
from tools import pmv4_e_canary_contract as contract
from tools import independent_component_release as generic


class FakeSigner:
    def __init__(self):
        self.args=[]
    def read_pinned_root_owner_public_key(self,*args,**kwargs):
        return object()
    def verify_exact_owner_release(self,signed,**kwargs):
        self.args.append(kwargs)
        assert kwargs["expected_candidate_sha"]==root.CANDIDATE
        assert kwargs["expected_rollback_sha"]=="0"*40
        assert kwargs["expected_scope_sha256"]==root.SCOPE_SHA
        assert kwargs["expected_manifest_sha256"]==root.MANIFEST_SHA
        assert kwargs["expected_freeze_sha256"]==root.FREEZE_SHA
        return {"approval_id":"owner-mcp-"+"a"*32}


def owner_fixture(tmp_path,monkeypatch):
    build="b"*40
    folder=tmp_path/("pmv4-e-canary-once-"+build)
    folder.mkdir(mode=0o700)
    proof=folder/"owner-proof.json"
    proof.write_bytes(root.canonical({
        "schema_version":"1.0","action":root.ACTION,
        "build_sha":build,"manifest_sha256":root.MANIFEST_SHA,
        "scope_sha256":root.SCOPE_SHA,
        "signed_owner_proof":{"synthetic":True},
    }))
    proof.chmod(0o400)
    # A GitHub Actions runner does not use AOT's UID 1000. The synthetic
    # fixture emulates a reviewed AOT-owned proof without ever relaxing
    # the production root verifier's exact UID check.
    original_lstat=Path.lstat
    def trusted_fixture_lstat(path):
        meta=original_lstat(path)
        if path==proof:
            return SimpleNamespace(
                st_mode=meta.st_mode,st_uid=1000,st_gid=meta.st_gid,
                st_nlink=meta.st_nlink,st_size=meta.st_size)
        return meta
    monkeypatch.setattr(Path,"lstat",trusted_fixture_lstat)
    monkeypatch.setattr(root,"stage_dir",lambda x:folder)
    fake=FakeSigner()
    monkeypatch.setattr(root,"installed_signer",lambda:fake)
    return build,proof,fake


def test_exact_owner_release_proof_requires_all_scoped_signer_bindings(
    tmp_path,monkeypatch,
):
    build,proof,signer=owner_fixture(tmp_path,monkeypatch)
    result,approval_id=root.signed_owner(build,{})
    assert result=={"synthetic":True}
    assert approval_id=="owner-mcp-"+"a"*32
    assert len(signer.args)==1
    assert signer.args[0]["expected_release_id"]=="release-"+root.CANDIDATE[:16]


@pytest.mark.parametrize("field,bad",[
    ("action","approval-other-action"),
    ("build_sha","a"*40),
    ("manifest_sha256","f"*64),
    ("scope_sha256","f"*64),
    ("schema_version","2.0"),
])
def test_mutated_signed_exact_action_proof_rejected(
    tmp_path,monkeypatch,field,bad,
):
    build,proof,signer=owner_fixture(tmp_path,monkeypatch)
    data=json.loads(proof.read_bytes());data[field]=bad
    proof.chmod(0o600)
    proof.write_bytes(root.canonical(data));proof.chmod(0o400)
    with pytest.raises(root.Denied,match="OWNER_EXACT_ACTION_NOT_MATCHED"):
        root.signed_owner(build,{})
    assert not signer.args


def test_replayed_owner_proof_with_wrong_mode_rejected(tmp_path,monkeypatch):
    build,proof,signer=owner_fixture(tmp_path,monkeypatch)
    proof.chmod(0o600)
    with pytest.raises(root.Denied,match="ONEUSE_OWNER_PROOF_UNTRUSTED"):
        root.signed_owner(build,{})
    assert not signer.args


def mock_production_root(tmp_path,monkeypatch):
    container=tmp_path/"root-control"
    (container/"receipts").mkdir(parents=True)
    (container/"active").mkdir()
    (container/"control").mkdir()
    policy_path=tmp_path/"protected-policy.json"
    prior={
        "schema_version":"1.0",
        "required_containers":["jason-runtime","jason-mcp-pilot"],
        "allowed_running_containers":[
            "jason-runtime","jason-mcp-pilot",
            "jason-pmv4-ticket-core","jason-pmv4-shadow-gateway",
        ],
        "required_user_units":["jason-release-manager.timer"],
        "required_system_units":["jason-core.service"],
    }
    original=json.dumps(prior,sort_keys=True).encode()+b"\n"
    policy_path.write_bytes(original)
    policy_sha=sha256(original).hexdigest()
    monkeypatch.setattr(root,"ROOT",container)
    monkeypatch.setattr(root,"RECEIPT",container/"control/owner-attempt.json")
    monkeypatch.setattr(root,"BACKUP",container/"control/backup-policy.json")
    monkeypatch.setattr(root,"CI",container/"control/protected-ci.json")
    monkeypatch.setattr(root,"POLICY",policy_path)
    monkeypatch.setattr(root,"POLICY_SHA",policy_sha)
    manifest={
        "candidate_sha":root.CANDIDATE,
        "rollback_sha":"0"*40,
        "component_id":"pmv4-e-canary",
        "provider_scope":contract.SCOPE,
    }
    approval="owner-mcp-"+"a"*32
    calls=[]
    monkeypatch.setattr(root,"preflight",lambda build_sha,strict_root:(
        calls.append(("preflight",strict_root))))
    monkeypatch.setattr(root,"candidate_packet",lambda:(
        manifest,{},{"manifest.json":b"{}"}))
    monkeypatch.setattr(root,"signed_owner",lambda build,m:(
        {"synthetic":True},approval))
    monkeypatch.setattr(root,"protected_status",lambda:{
        "jason-runtime":("id","image","started"),
        "jason-pmv4-ticket-core":("id2","image2","started2"),
    })
    def stage(build,manifest,signed,owner,before):
        calls.append(("stage",owner))
        (container/"receipts"/("owner-"+approval+".json")).write_bytes(
            root.canonical({
                "state":"accepted","component_id":"pmv4-e-canary",
                "approval_id":approval,"candidate_sha":root.CANDIDATE,
            }))
        root.CI.write_bytes(root.canonical({
            "candidate_sha":root.CANDIDATE,
            "reviewed_root_build_sha":build,
        }))
    monkeypatch.setattr(root,"stage_root",stage)
    monkeypatch.setattr(root,"source_bytes",lambda build,name:
        (Path(__file__).resolve().parents[1]/
         "pmv4_e_canary_drift_policy.py").read_bytes())
    def root_write(path,payload,mode=0o600,uid=0):
        calls.append(("write",path.name))
        path.write_bytes(root.canonical(payload))
    monkeypatch.setattr(root,"root_json",root_write)
    def root_replace(path,content,required_old_sha):
        assert sha256(path.read_bytes()).hexdigest()==required_old_sha
        path.write_bytes(content)
    monkeypatch.setattr(root,"root_replace",root_replace)
    import tools.independent_component_release as generic
    monkeypatch.setattr(generic,"trusted_file",
        lambda path,**kw:path.read_bytes())
    def accepted():
        calls.append(("native",root.POLICY.read_bytes()))
        return {
            "status":"providerfree_native_generic_controller_accepted",
            "source_sha":root.CANDIDATE,
            "component_id":"pmv4-e-canary",
            "provider_writes":0,
            "protected_service_restarts":0,
            "retirement_authorized":False,
        }
    monkeypatch.setattr(root,"native_release",accepted)
    def cleanup(build_sha,accepted):
        calls.append(("cleanup",accepted))
        backup=json.loads(root.BACKUP.read_bytes())
        root.POLICY.write_bytes(bytes.fromhex(backup["original_policy_hex"]))
    monkeypatch.setattr(root,"cleanup",cleanup)
    return calls,container,policy_path,original


def test_root_action_accepts_then_rolls_back_only_canary(
    tmp_path,monkeypatch,
):
    calls,container,policy,original=mock_production_root(tmp_path,monkeypatch)
    result=root.execute("b"*40)
    assert result["state"]=="accepted_and_removed"
    assert result["native_generic_acceptance_verified"] is True
    assert result["isolated_canary_rollback_verified"] is True
    assert result["production_freeze_unchanged"] is True
    assert result["pmv3_units_modified"] is False
    assert result["retirement_authorized"] is False
    assert policy.read_bytes()==original
    assert [t[0] for t in calls].index("preflight")<[
        t[0] for t in calls].index("stage")<[
        t[0] for t in calls].index("native")<[
        t[0] for t in calls].index("cleanup")
    assert json.loads((container/"control"/(
        "pmv4-e-canary-"+root.CANDIDATE+"-accepted.json")).read_bytes())[
        "state"]=="accepted_and_removed"


def test_failed_native_acceptance_runs_only_cleanup_and_no_terminal_success(
    tmp_path,monkeypatch,
):
    calls,container,policy,original=mock_production_root(tmp_path,monkeypatch)
    def fail():
        calls.append(("native_failed",None))
        raise PermissionError("synthetic native denied")
    monkeypatch.setattr(root,"native_release",fail)
    with pytest.raises(PermissionError,match="synthetic native denied"):
        root.execute("b"*40)
    assert policy.read_bytes()==original
    assert ("cleanup",False) in calls
    assert not (container/"control"/(
        "pmv4-e-canary-"+root.CANDIDATE+"-accepted.json")).exists()


def test_protected_policy_changed_between_preflight_and_activation_denies(
    tmp_path,monkeypatch,
):
    calls,container,policy,original=mock_production_root(tmp_path,monkeypatch)
    before=json.loads(policy.read_bytes())
    before["required_user_units"].append("unexpected")
    policy.write_bytes(root.canonical(before)+b"\n")
    # The attested policy is compiled from the exact source blob into an
    # isolated module; its exception is intentionally not the ambient import.
    with pytest.raises(PermissionError,
                       match="ROOT_POLICY_BASELINE_SHA_CHANGED"):
        root.execute("b"*40)
    assert not any(a[0]=="native" for a in calls)


def test_oneowner_source_never_disables_watchdog_or_promotes_pmv3():
    src=Path(root.__file__).read_text()
    assert "systemctl disable" not in src
    assert "force_close_breaker" not in src
    assert "restart jason-runtime" not in src
    assert '"retirement_authorized":False' in src
    assert 'native_release()' in src
    assert 'cleanup(build_sha,accepted=True)' in src


def test_only_empty_private_canary_network_may_be_removed(monkeypatch):
    calls=[]
    class Result:
        def __init__(self,stdout="",returncode=0):
            self.stdout=stdout;self.returncode=returncode
    def call(argv,**kwargs):
        calls.append(list(argv))
        if argv[1:3]==["network","inspect"]:
            return Result(json.dumps([{
                "Name":"jason-pmv4-e-canary-private",
                "Driver":"bridge","Internal":True,"Attachable":False,
                "Containers":{},
                "Labels":{"com.docker.compose.project":"jason-pmv4-e-canary"},
            }]))
        if argv[1:3]==["network","rm"]:
            return Result("")
        if argv[1:3]==["network","ls"]:
            return Result("")
        raise AssertionError("Unexpected Docker command: "+repr(argv))
    monkeypatch.setattr(root.subprocess,"run",call)
    assert root.remove_exact_orphaned_canary_network() is True
    assert len([x for x in calls if x[1:3]==["network","rm"]])==1
    assert all(x[:2]==["/usr/bin/docker","network"] for x in calls)


@pytest.mark.parametrize("violation",[
    ("Internal",False),
    ("Driver","overlay"),
    ("Attachable",True),
    ("Containers",{"foreign-id":{}}),
    ("Name","jason-core"),
    ("Labels",{"com.docker.compose.project":"jason-core"}),
])
def test_private_canary_network_never_removes_foreign_or_connected_peers(
    monkeypatch,violation,
):
    calls=[]
    class Result:
        def __init__(self,stdout="",returncode=0):
            self.stdout=stdout;self.returncode=returncode
    def call(argv,**kwargs):
        calls.append(argv)
        if argv[1:3]==["network","inspect"]:
            item={
                "Name":"jason-pmv4-e-canary-private",
                "Driver":"bridge","Internal":True,"Attachable":False,
                "Containers":{},
                "Labels":{"com.docker.compose.project":"jason-pmv4-e-canary"},
            }
            item[violation[0]]=violation[1]
            return Result(json.dumps([item]))
        raise AssertionError("No network mutation allowed")
    monkeypatch.setattr(root.subprocess,"run",call)
    with pytest.raises(root.Denied,match="FOREIGN_PEER_OR_POLICY"):
        root.remove_exact_orphaned_canary_network()
    assert len(calls)==1
