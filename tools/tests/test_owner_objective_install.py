"""Full Root installation/reverse transaction using disposable paths only.

Docker, systemd, GitHub and identity mutation are replaced by typed local ports.
No Jason directory, provider, key, credential or service is accessed.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest
from tools import owner_objective_install as install
from tools import owner_objective_install_scope as contract

pytestmark=pytest.mark.skipif(os.geteuid()!=0,reason="disposable UID0 filesystem test")


@pytest.fixture
def tx(tmp_path,monkeypatch):
    root=tmp_path
    paths={
      "BASE":root/"usr/owner-objective","CONFIG":root/"etc/owner-objective.json",
      "PRIVATE":root/"private/objectives","SPOOL":root/"private/inbox","STATE":root/"openclaw/owner-objective",
      "OLD_PLANS":root/"openclaw/universal-approvals.sqlite3","AUTHORITY":root/"authority/authority.sqlite3",
      "BINDINGS":root/"bindings/bindings.sqlite3","KEYS":root/"unused-keys.json",
      "TOKEN":root/"token","ROOT_POLICY":root/"etc/production-desired-state.json",
      "DOC_BASE":root/"publisher","DOC_OVERRIDE":root/"systemd/publisher.d/20-reviewed-publisher.conf",
      "MARKER":root/"marker.json","SYSTEMD":root/"systemd",
    }
    for name,value in paths.items():monkeypatch.setattr(install,name,value)
    monkeypatch.setattr(install,"PUBLIC",paths["BASE"]/"public")
    monkeypatch.setattr(install,"TRUSTED",paths["BASE"]/"trusted")
    monkeypatch.setattr(install,"INSTALL",paths["PRIVATE"]/"installation")
    for directory in (root/"usr",root/"etc",root/"private",root/"openclaw",root/"authority",
                      root/"bindings",root/"publisher",root/"systemd",root/"manager",root/"native"):
        directory.mkdir(mode=0o755)
    os.chown(root/"openclaw",1000,1000)
    for name,raw in (("ROOT_POLICY",b"exact original policy"),("MARKER",b'{"state":"accepted"}'),("TOKEN",b"test-only-bot-token")):
        paths[name].write_bytes(raw);paths[name].chmod(0o600 if name!="MARKER" else 0o444)
    os.chown(paths["TOKEN"],1000,1000)
    with sqlite3.connect(paths["OLD_PLANS"]) as db:
        db.execute("CREATE TABLE prior_decisions (id PRIMARY KEY,value)")
        db.execute("INSERT INTO prior_decisions VALUES (1,'retain-original')")
    os.chown(paths["OLD_PLANS"],1000,1000);paths["OLD_PLANS"].chmod(0o600)
    with sqlite3.connect(paths["AUTHORITY"]) as db:
        db.execute("CREATE TABLE grants (id PRIMARY KEY,payload)")
    unit=root/"systemd/jason-documentation-reconciliation.service"
    unit.write_bytes(b"exact original service");unit.chmod(0o644)
    protection={}
    for name,mode in (("freeze",0o600),("hold",0o664),("worker",0o755),("pause",0o600)):
        path=root/name;path.write_bytes(name.encode());path.chmod(mode)
        if name!="worker":os.chown(path,1000,1000)
        protection[name]=path
    native=root/"native/code.py";native.write_bytes(b"unchanged accepted code");native.chmod(0o444)
    peers={name:dict(id=name+"-id",image="sha256:"+"1"*64,started_at="before") for name in
        ("jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core","jason-pmv4-shadow-gateway","jason-teams-gateway","openbao")}
    original_gateway=dict(Id=peers["jason-teams-gateway"]["id"],Image=peers["jason-teams-gateway"]["image"],
                          Config={"Env":["PRIVATE_TEST_ONLY=not-a-real-credential"]})
    current_gateway=deepcopy(original_gateway)
    current_peers=deepcopy(peers)
    root_path={"active":False}
    manifest={key:"unchanged" for key in ("revision","runtime_revision","runtime_image_id","mcp_revision","mcp_image_id",
        "host_revision","host_release","release_manager_source_revision","mobile_release_approval_policy_digest","mobile_release_approval_mode")}
    control={"circuit_breaker":{"state":"closed"},"last_known_good":{"release_id":"release-test","manifest":manifest}}
    for name,value in (("production-control-state.json",control),("production-drift.json",{"status":"pass","problems":[]})):
        (root/"manager"/name).write_bytes(install.canonical(value));(root/"manager"/name).chmod(0o600)
    effects=[]
    def write(path,raw,mode=0o400,uid=0):
        assert root in path.parents
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        with os.fdopen(fd,"wb") as stream:
            os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),uid,uid)
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
    def directory(path,uid,mode=None):
        assert root==path or root in path.parents
        assert path.is_dir() and not path.is_symlink()
        assert path.stat().st_uid==uid
        if mode is not None:assert path.stat().st_mode&0o777==mode
    def user_python(code,*args,**kwargs):
        effects.append(("uid1000",code))
        if code==install.GRANT_WRITE:
            with sqlite3.connect(paths["AUTHORITY"]) as db:
                for g in json.loads(args[1]):db.execute("INSERT INTO grants VALUES (?,?)",(g["grant_id"],json.dumps(g)))
        elif code==install.GRANT_REVOKE:
            with sqlite3.connect(paths["AUTHORITY"]) as db:
                for g in json.loads(args[1]):
                    g["status"]="revoked";db.execute("UPDATE grants SET payload=? WHERE id=?",(json.dumps(g),g["grant_id"]))
        elif "p.mkdir" in code:
            path=Path(args[0]);path.mkdir(mode=int(args[1],8));os.chown(path,1000,1000)
        elif "wal_checkpoint" in code:
            with sqlite3.connect(args[0]) as db:db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        elif "os.symlink" in code:
            os.rename(args[0],args[1]);os.symlink(args[1],args[0]);os.lchown(args[0],1000,1000)
        elif "os.unlink" in code:
            os.unlink(args[0]);os.rename(args[1],args[0])
        elif "request_root_control_transition" in code:
            effects.append(("native_lkg",None))
        else:raise AssertionError("unregistered user operation")
        return ""
    def run(args,**kwargs):
        nonlocal current_gateway
        effects.append(("run",args))
        if args[0]=="/usr/bin/python3":
            current_gateway=dict(Id="new-gateway-id",Image="sha256:"+"3"*64)
            current_peers["jason-teams-gateway"].update(id="new-gateway-id",image="sha256:"+"3"*64,started_at="after")
        elif args[:3]==["/usr/bin/docker","inspect","jason-owner-objective"]:
            return json.dumps([{"State":{"Running":True,"Health":{"Status":"healthy"}}}])
        elif args[:2]==["/usr/bin/docker","inspect"]:
            return json.dumps([current_gateway if args[2]=="jason-teams-gateway" else original_gateway])
        elif args[:2]==["/usr/bin/docker","rename"]:
            current_gateway=deepcopy(original_gateway)
        return ""
    def systemctl(args,**kwargs):
        effects.append(("systemctl",args))
        if args[0] in ("enable","disable"):root_path["active"]=args[0]=="enable"
    c=dict(write=write,read=lambda p,*a:p.read_bytes(),directory=directory,sync_dir=lambda p:None,
        user_python=user_python,run=run,systemctl=systemctl,peers=lambda:deepcopy(current_peers),
        props=lambda *a:{"ActiveState":"active" if root_path["active"] else "inactive"},
        MANAGER=root/"manager",PAUSE=protection["pause"],NATIVE=root/"native")
    ns=dict(FREEZE=protection["freeze"],HOLD=protection["hold"],
        FREEZE_HASH=sha256(b"freeze").hexdigest(),HOLD_HASH=sha256(b"hold").hexdigest(),
        WORKER_BEFORE=sha256(b"worker").hexdigest())
    rows=contract.grants(install.OWNER,install.SERVICE)
    scope=dict(candidate_sha="a"*40,artifacts={"component_image":"sha256:"+"2"*64,"gateway_image":"sha256:"+"3"*64},
        canonical_plan_rows_sha256=install.plan_database(c),
        campaign=dict(deny_approval_id="planapproval-objective-"+"0"*32,approve_approval_id="planapproval-objective-"+"1"*32,
                      issued_at=datetime.now(timezone.utc).isoformat()),
        protected_peers=peers,owner_pause_sha256=sha256(b"pause").hexdigest(),
        protection_files={str(protection[k]):sha256(k.encode()).hexdigest() for k in ("freeze","hold","worker")},
        trusted_code_sha256={"tools/deploy_live_container.py":sha256(b"source-only").hexdigest()},
        adopted_policy_sha256="d"*64,teams_proactive_token_sha256=sha256(paths["TOKEN"].read_bytes()).hexdigest())
    facts=dict(code={"tools/deploy_live_container.py":b"source-only"},policy_raw=paths["ROOT_POLICY"].read_bytes(),
        policy_after={"exact":"reviewed-delta"},key=dict(pem="not-real-public-key",key_id="gateway",fingerprint="f"*64,
        machine_identity="test-gateway"),grants=rows,control=control,gateway=original_gateway,
        marker=paths["MARKER"].read_bytes(),native={"code.py":sha256(native.read_bytes()).hexdigest()},
        scope_module=contract)
    monkeypatch.setattr(install,"trusted_source",lambda c,candidate,name:b"reviewed unit")
    transaction=install.Installation(c,ns,"a"*40,scope,facts)
    return transaction,root,effects


def test_installation_cannot_send_cards_before_native_acceptance(tx):
    t,root,effects=tx
    t.apply("verified-owner")
    assert json.loads((install.PUBLIC/"activation.json").read_bytes())["ready"] is False
    assert install.OLD_PLANS.is_symlink()
    t.replace_gateway();t.seal_profiles();t.start_component()
    assert json.loads((install.PUBLIC/"activation.json").read_bytes())["ready"] is False
    profile=json.loads((install.PUBLIC/"profile.json").read_bytes())
    root_config=json.loads(install.CONFIG.read_bytes())
    assert profile["spool"]=="/var/lib/jason/owner-objective-inbox"
    assert len(root_config["required_grants_sha256"])==6
    t.native_acceptance()
    assert json.loads((install.PUBLIC/"activation.json").read_bytes())["ready"] is True
    assert (install.INSTALL/"accepted.json").exists()
    assert any(item[0]=="native_lkg" for item in effects)


def test_reverse_rollback_preserves_newer_canonical_decisions_and_private_evidence(tx):
    t,root,effects=tx
    t.apply("verified-owner");t.replace_gateway();t.seal_profiles();t.start_component()
    with sqlite3.connect(install.STATE/"universal-approvals.sqlite3") as db:
        db.execute("INSERT INTO prior_decisions VALUES (2,'retain-newer-decision')")
    t.restore()
    assert not install.OLD_PLANS.is_symlink()
    with sqlite3.connect(install.OLD_PLANS) as db:
        assert db.execute("SELECT value FROM prior_decisions ORDER BY id").fetchall()==[
            ("retain-original",),("retain-newer-decision",)]
    assert (install.INSTALL/"approval.json").exists()
    assert (install.INSTALL/"gateway-before.json").stat().st_mode&0o777==0o400
    assert install.ROOT_POLICY.read_bytes()==b"exact original policy"
    assert not install.CONFIG.exists()
    with sqlite3.connect(install.AUTHORITY) as db:
        assert all(json.loads(row[0])["status"]=="revoked" for row in db.execute("SELECT payload FROM grants"))


def test_nonisolated_entrypoint_denies_before_any_native_access(monkeypatch):
    monkeypatch.setattr(install,"primitives",lambda:pytest.fail("private access before guard"))
    with pytest.raises(PermissionError,match="EXACT_ISOLATED_ROOT"):install.main(["--source-sha","a"*40])
