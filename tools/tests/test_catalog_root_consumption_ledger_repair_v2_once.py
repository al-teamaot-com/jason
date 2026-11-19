"""One-use three-file catalog root trust correction, strong rollback guarantees."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE=Path(__file__).resolve().parents[1]/"catalog_root_consumption_ledger_repair_v2_once.py"
spec=importlib.util.spec_from_file_location("test_catalog_ledger_isolated_v2_root_once",SOURCE)
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_entra_device_grant_correct_and_exact_consent_required(monkeypatch):
    calls=[]
    fake=SimpleNamespace(TENANT="synthetic-tenant",CLIENT_ID="synthetic-client",
                         SCOPE="synthetic-scope",jwt_owner=lambda t:"synthetic-verified-owner")
    def _form(url,args):
        calls.append((url,dict(args)))
        if url.endswith("/devicecode"):
            return {"device_code":"never-real","user_code":"synthetic",
                    "verification_uri":"https://login.microsoft.com/device",
                    "expires_in":600,"interval":5}
        return {"access_token":"synthetic-not-real"}
    fake._form=_form
    module_spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda obj:None))
    monkeypatch.setattr(m.importlib.util,"spec_from_file_location",lambda *a:module_spec)
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda *a:fake)
    monkeypatch.setattr(m.time,"sleep",lambda _:None)
    monkeypatch.setattr("builtins.input",lambda prompt:m.WORD)
    assert m.auth_owner("a"*40,"b"*64)=="synthetic-verified-owner"
    assert calls[-1][1]["grant_type"]=="urn:ietf:params:oauth:grant-type:device_code"
    monkeypatch.setattr("builtins.input",lambda prompt:"NO")
    with pytest.raises(PermissionError,match="EXACT_OWNER_DECISION_MISSING"):
        m.auth_owner("a"*40,"b"*64)


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    root=tmp_path/"root-bundle"
    root.mkdir()
    host=root/"catalog_scoped_promotion_host.py"
    router=root/"catalog_scoped_promotion_root.py"
    policy=tmp_path/"catalog-root-policy.json"
    originals=(b"original host bytecode",b"original router bytecode",
               b'{"root-policy":"prior"}\n')
    changes=(b"changed host strict reader",b"changed router fresh owner lineage",
             b'{"root-policy":"new"}\n')
    for path,data,mode in zip((host,router,policy),originals,(0o644,0o644,0o600)):
        path.write_bytes(data);path.chmod(mode)
    shadow=tmp_path/"shadow-lock"
    native=tmp_path/"production-lock"
    for path in (shadow,native):
        path.write_bytes(b"")
        path.chmod(0o600)
    state=tmp_path/"state"
    state.mkdir()
    freeze=state/"production-deployment-freeze"
    freeze.write_bytes(b'{"freeze":"original"}\n')
    ledger=tmp_path/"immutable-one-use-ledger"
    for key,value in {
        "ROOT_MODULE":host,"ROOT_ROUTER":router,"ROOT_POLICY":policy,
        "NATIVE_LOCK":native,"SHADOW_LOCK":shadow,"LEDGER":ledger,"STATE":state
    }.items():monkeypatch.setattr(m,key,value)
    for key,data in zip(("OLD_MODULE_SHA","OLD_ROUTER_SHA","ROOT_POLICY_SHA"),originals):
        monkeypatch.setattr(m,key,m.digest(data))
    for key,data in zip(("NEW_MODULE_SHA","NEW_ROUTER_SHA"),changes):
        monkeypatch.setattr(m,key,m.digest(data))
    snap={"containers":{"jason-runtime":("id","image","start"),
                        "jason-pmv4-ticket-core":("id2","image2","start2")},
          "runbook":{"ActiveState":"active","MainPID":"44"}}
    preflight=("b"*40,*changes,snap,freeze.read_bytes())
    monkeypatch.setattr(m,"preflight",lambda:preflight)
    monkeypatch.setattr(m,"auth_owner",lambda *a:"synthetic-approved-owner")
    monkeypatch.setattr(m,"trusted_release_lock",lambda *a:True)
    monkeypatch.setattr(m,"trusted",lambda path,**kw:Path(path).read_bytes())
    monkeypatch.setattr(m,"container_snapshot",lambda:snap)
    monkeypatch.setattr(m,"verified_main",lambda:"b"*40)
    def fake_replace(path,data,mode=0o644):
        path.write_bytes(data);path.chmod(mode)
    monkeypatch.setattr(m,"replace",fake_replace)
    # The clean native root loader now runs in a separate interpreter.
    monkeypatch.setattr(m,"verify_trusted_root_isolated",lambda sha:{
        "status":"trusted_catalog_root_verified_in_isolated_process",
        "source_sha":sha,"root_owner":True})
    return (host,router,policy),originals,changes,ledger,freeze


def test_exact_three_file_install_durable_owner_intent_and_verified_readback(fixture):
    paths,originals,changes,ledger,freeze=fixture
    m.execute()
    for p,new in zip(paths,changes):assert p.read_bytes()==new
    assert (ledger/"original-root-host.bin").read_bytes()==originals[0]
    assert (ledger/"original-root-router.bin").read_bytes()==originals[1]
    assert (ledger/"original-root-policy.bin").read_bytes()==originals[2]
    intent=m.json.loads((ledger/"owner-intent.json").read_text())
    assert intent["status"]=="consumed_before_mutation"
    assert intent["new_host_sha256"]==m.digest(changes[0])
    assert intent["new_router_sha256"]==m.digest(changes[1])
    assert intent["new_policy_sha256"]==m.digest(changes[2])
    assert not intent["image_promotion_approved"] and not intent["autotask_provider_writes_approved"]
    verified=m.json.loads((ledger/"verified.json").read_text())
    assert verified["status"]=="exact_catalog_bootstrap_mcp_ledger_isolated_postcheck_verified"
    assert not verified["historical_ledger_entries_changed"]
    assert verified["native_trust_isolated_receipt"]["root_owner"] is True
    assert not (ledger/"failed.json").exists()


@pytest.mark.parametrize("failing_step",["new_host","new_router","new_policy","root_worker","postflight"])
def test_any_scoped_mutation_failure_restores_three_originals(fixture,monkeypatch,failing_step):
    paths,originals,changes,ledger,freeze=fixture
    real_replace=m.replace
    failure_once=[False]
    def maybe_fail(path,data,mode=0o644):
        real_replace(path,data,mode)
        idx=list(paths).index(path)
        if not failure_once[0] and failing_step==(
            ("new_host","new_router","new_policy")[idx]):
            failure_once[0]=True
            raise RuntimeError("synthetic atomic swap error after bytes written")
    monkeypatch.setattr(m,"replace",maybe_fail)
    if failing_step=="root_worker":
        def reject(sha):
            raise PermissionError("synthetic isolated root loader rejected")
        monkeypatch.setattr(m,"verify_trusted_root_isolated",reject)
    if failing_step=="postflight":
        counter=[0]
        def changing_snapshot():
            counter[0]+=1
            if counter[0]==1:
                return {"unexpected":"synthetic regression"}
            return {"containers":{"jason-runtime":("id","image","start"),
                                   "jason-pmv4-ticket-core":("id2","image2","start2")},
                    "runbook":{"ActiveState":"active","MainPID":"44"}}
        monkeypatch.setattr(m,"container_snapshot",changing_snapshot)
    if failing_step=="postflight":
        with pytest.raises(PermissionError,match="PMV4_OR_CATALOG_CONTAINER_CHANGED"):
            m.execute()
    elif failing_step=="root_worker":
        with pytest.raises(PermissionError,match="synthetic isolated root loader"):
            m.execute()
    else:
        with pytest.raises(RuntimeError,match="synthetic atomic"):
            m.execute()
    for p,original in zip(paths,originals):
        assert p.read_bytes()==original
    receipt=m.json.loads((ledger/"failed.json").read_text())
    assert receipt["status"]=="rolled_back" and receipt["rollback_verified"]
    assert not (ledger/"verified.json").exists()


def test_three_file_root_repair_never_changes_approval_ledger_runtime_or_pmv4():
    code=SOURCE.read_text()
    for forbidden in ("docker','stop","docker','run","docker','rm",
                      "systemctl','restart","systemctl','stop",
                      "production-deployment-freeze.unlink"):
        assert forbidden not in code
    assert "IMAGE_PROMOTION=false; PROVIDER_WRITES=false" in code
    assert "AUTH/" in code and "ROOT_CATALOG/" in code
    assert 'ROOT_ROUTER=Path(' in code
    assert 'ROOT_MODULE=Path(' in code
    assert 'ROOT_POLICY=Path(' in code
    assert 'ledger' in code.lower()


def test_true_new_interpreter_prevents_previous_catalog_namespace_contamination(monkeypatch):
    import sys
    import tools
    import implementation
    assert "tools" in sys.modules
    assert "implementation" in sys.modules
    # For this test only, swap the native root-only statements for equivalent
    # synthetic namespace assertions. The PRODUCTION constant remains pinned.
    simulated='''
import json,sys
if any(n in sys.modules for n in ("tools","implementation","implementation.kernel")):
    raise RuntimeError("UNTRUSTED_PREEXISTING_IMPORT_NAMESPACE")
print(json.dumps({"status":"trusted_catalog_root_verified_in_isolated_process",
                  "source_sha":sys.argv[1],"root_owner":True}))
'''
    monkeypatch.setattr(m,"ISOLATED_ROOT_CHECK",simulated)
    result=m.verify_trusted_root_isolated("a"*40)
    assert result["source_sha"]=="a"*40
    assert result["root_owner"] is True


@pytest.mark.parametrize("script",[
    "import sys; raise RuntimeError('UNTRUSTED_PREEXISTING_IMPORT_NAMESPACE')",
    "print('{\"status\":\"wrong\"}')",
    "print('{\"status\":\"trusted_catalog_root_verified_in_isolated_process\","
    "\"source_sha\":\"falsified\",\"root_owner\":true}')",
])
def test_isolated_process_failure_or_untrusted_receipt_must_trigger_parent_rollback(monkeypatch,script):
    monkeypatch.setattr(m,"ISOLATED_ROOT_CHECK",script)
    with pytest.raises(PermissionError,match="ISOLATED_TRUST"):
        m.verify_trusted_root_isolated("a"*40)


def test_native_trust_uses_exact_isolated_interpreter_and_clean_environment(monkeypatch):
    recorded={}
    def pretend_run(argv,**opts):
        recorded["argv"]=argv
        recorded["kwargs"]=opts
        return SimpleNamespace(returncode=0,
            stdout=m.json.dumps({
                "status":"trusted_catalog_root_verified_in_isolated_process",
                "source_sha":"b"*40,"root_owner":True}).encode(),
            stderr=b"")
    monkeypatch.setattr(m.subprocess,"run",pretend_run)
    m.verify_trusted_root_isolated("b"*40)
    assert recorded["argv"][:3]==["/usr/bin/python3","-I","-c"]
    assert recorded["kwargs"]["cwd"]=="/"
    assert recorded["kwargs"]["timeout"]<=120
    assert recorded["kwargs"]["check"] is False
    assert "PYTHONPATH" not in recorded["kwargs"]["env"]
    assert "PATH" in recorded["kwargs"]["env"]
    assert "tools" in recorded["argv"][3] or "tools" in recorded["argv"][2]


@pytest.mark.parametrize("status,rollback",[
    ("rollback_unverified",False),
    ("rolled_back",False),
    ("installed",True),
])
def test_v1_install_recovery_does_not_accept_unverified_rollback(tmp_path,monkeypatch,status,rollback):
    root=tmp_path/"catalog-private"
    previous=root/"root-consumption-ledger-reader-repair-oneuse"
    previous.mkdir(parents=True,mode=0o700)
    previous.chmod(0o700)
    monkeypatch.setattr(m,"ROOT_CATALOG",root)
    real_stat=Path.stat
    def root_dir_stat(p,*args,**kwargs):
        meta=real_stat(p,*args,**kwargs)
        if p==previous:
            return SimpleNamespace(st_uid=0,st_mode=meta.st_mode)
        return meta
    monkeypatch.setattr(Path,"stat",root_dir_stat)
    monkeypatch.setattr(m,"trusted",lambda path,**kw:Path(path).read_bytes())
    original={
        "status":"consumed_before_mutation",
        "action":"catalog-root-bootstrap-mcp-consumption-ledger-separation-v1",
        "approval_id":"owner-test-opaque",
        "old_host_sha256":m.OLD_MODULE_SHA,
        "new_host_sha256":m.NEW_MODULE_SHA,
        "old_router_sha256":m.OLD_ROUTER_SHA,
        "new_router_sha256":m.NEW_ROUTER_SHA,
        "image_promotion_approved":False,
        "autotask_provider_writes_approved":False,
    }
    (previous/"owner-intent.json").write_text(m.json.dumps(original))
    (previous/"failed.json").write_text(m.json.dumps({"status":status,"rollback_verified":rollback}))
    if status=="rolled_back" and rollback is True:
        assert m.first_oneuse_failed_and_rolled_back()=="owner-test-opaque"
    else:
        with pytest.raises(PermissionError,match="ORIGINAL_ONEUSE_INSTALL_ROLLBACK_NOT_VERIFIED"):
            m.first_oneuse_failed_and_rolled_back()
    assert (previous/"owner-intent.json").exists()
    assert (previous/"failed.json").exists()


def test_v1_rolled_back_journal_accepted_read_only(tmp_path,monkeypatch):
    root=tmp_path/"catalog-private"
    previous=root/"root-consumption-ledger-reader-repair-oneuse"
    previous.mkdir(parents=True,mode=0o700)
    previous.chmod(0o700)
    monkeypatch.setattr(m,"ROOT_CATALOG",root)
    real_stat=Path.stat
    monkeypatch.setattr(Path,"stat",lambda path,*a,**kw:
        SimpleNamespace(st_uid=0,st_mode=real_stat(path,*a,**kw).st_mode)
        if path==previous else real_stat(path,*a,**kw))
    monkeypatch.setattr(m,"trusted",lambda path,**kw:Path(path).read_bytes())
    prior={
        "status":"consumed_before_mutation",
        "action":"catalog-root-bootstrap-mcp-consumption-ledger-separation-v1",
        "approval_id":"owner-old-approved",
        "old_host_sha256":m.OLD_MODULE_SHA,
        "new_host_sha256":m.NEW_MODULE_SHA,
        "old_router_sha256":m.OLD_ROUTER_SHA,
        "new_router_sha256":m.NEW_ROUTER_SHA,
        "image_promotion_approved":False,
        "autotask_provider_writes_approved":False,
    }
    (previous/"owner-intent.json").write_text(m.json.dumps(prior))
    (previous/"failed.json").write_text(m.json.dumps({"status":"rolled_back","rollback_verified":True}))
    assert m.first_oneuse_failed_and_rolled_back()=="owner-old-approved"


def test_isolated_root_guard_is_preserved_in_native_worker_source():
    import inspect
    import tools.catalog_scoped_promotion_root as original
    loader=Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
    source=loader.read_text()
    assert 'CATALOG_SCOPED_ROOT_IMPORT_NAMESPACE_UNTRUSTED' in source
    assert 'any(name in sys.modules' in source
    assert "worker._trusted_catalog_scoped_promotion_module(source)" in m.ISOLATED_ROOT_CHECK
    assert "trusted.CatalogPMv4ProtectedHost" in m.ISOLATED_ROOT_CHECK
    assert "host.enforce_installed_production_trust()" in m.ISOLATED_ROOT_CHECK
    assert "importlib.util.spec_from_file_location" in m.ISOLATED_ROOT_CHECK
