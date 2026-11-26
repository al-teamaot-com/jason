"""One-use three-file catalog root trust correction, strong rollback guarantees."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE=Path(__file__).resolve().parents[1]/"catalog_root_consumption_ledger_repair_once.py"
spec=importlib.util.spec_from_file_location("test_catalog_ledger_three_file_root_once",SOURCE)
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
    class Trusted:
        execute_native_catalog_scoped_request=lambda *a:None
        class CatalogPMv4ProtectedHost:
            def __init__(self,repo):pass
            def enforce_installed_production_trust(self):pass
    class Worker:
        def _trusted_catalog_scoped_promotion_module(self,source):
            return Trusted()
    mockspec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda obj:None))
    monkeypatch.setattr(m.importlib.util,"spec_from_file_location",lambda *a:mockspec)
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda *a:Worker())
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
    assert verified["status"]=="exact_catalog_bootstrap_mcp_ledger_reader_verified"
    assert not verified["historical_ledger_entries_changed"]
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
        def reject(*a):
            raise PermissionError("synthetic trusted module rejected")
        class Refuse:
            def _trusted_catalog_scoped_promotion_module(self,sha):
                return reject()
        monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda spec:Refuse())
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
        with pytest.raises(PermissionError,match="synthetic trusted"):
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
