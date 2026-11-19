"""One-use exact root installer: Entra consent, prior scope and paired root restore."""
from __future__ import annotations
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

SOURCE=Path(__file__).resolve().parents[1]/"catalog_root_consumption_ledger_repair_once.py"
spec=importlib.util.spec_from_file_location("test_catalog_consumption_ledger_root_once",SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_entra_exact_scoped_owner_consent_with_correct_device_grant(monkeypatch):
    calls=[]
    fake=SimpleNamespace(TENANT="synthetic-tenant",CLIENT_ID="synthetic-client",
                         SCOPE="synthetic-scope",jwt_owner=lambda t:"synthetic-verified-owner")
    def response(url,args):
        calls.append((url,dict(args)))
        if url.endswith("/devicecode"):
            return {"device_code":"not-a-real-device-code","user_code":"synthetic",
                    "verification_uri":"https://login.microsoft.com/device",
                    "expires_in":600,"interval":5}
        return {"access_token":"synthetic-access-token-not-real"}
    fake._form=response
    mockspec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
    monkeypatch.setattr(m.importlib.util,"spec_from_file_location",lambda *a:mockspec)
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda *a:fake)
    monkeypatch.setattr(m.time,"sleep",lambda *_:None)
    monkeypatch.setattr("builtins.input",lambda _:m.WORD)
    assert m.auth_owner("a"*40,"b"*64)=="synthetic-verified-owner"
    assert calls[1][1]["grant_type"]=="urn:ietf:params:oauth:grant-type:device_code"
    monkeypatch.setattr("builtins.input",lambda _:"NOT APPROVED")
    with pytest.raises(PermissionError,match="EXACT_OWNER_DECISION_MISSING"):
        m.auth_owner("a"*40,"b"*64)


@pytest.fixture
def scenario(tmp_path,monkeypatch):
    old=b"original trusted root catalog handler"
    new=b"new reviewed unsigned restage and PMv4 protected handler"
    rootmodule=tmp_path/"catalog_scoped_promotion_root.py"
    rootmodule.write_bytes(old);rootmodule.chmod(0o644)
    native=tmp_path/"production-transaction.lock"
    shadow=tmp_path/"shadow-host-mutation.lock"
    native.write_bytes(b"");shadow.write_bytes(b"")
    native.chmod(0o600);shadow.chmod(0o600)
    state=tmp_path/"state";state.mkdir()
    freeze=state/"production-deployment-freeze"
    freeze.write_bytes(b'{"status":"active"}\n')
    ledger=tmp_path/"oneuse-audit"
    monkeypatch.setattr(m,"ROOT_MODULE",rootmodule)
    monkeypatch.setattr(m,"NATIVE_LOCK",native)
    monkeypatch.setattr(m,"SHADOW_LOCK",shadow)
    monkeypatch.setattr(m,"LEDGER",ledger)
    monkeypatch.setattr(m,"STATE",state)
    monkeypatch.setattr(m,"OLD_MODULE_SHA",m.digest(old))
    monkeypatch.setattr(m,"NEW_MODULE_SHA",m.digest(new))
    snap={"containers":{"jason-runtime":("x","y","z")},"runbook":{"ActiveState":"active"}}
    monkeypatch.setattr(m,"preflight",lambda:("a"*40,new,snap,freeze.read_bytes()))
    monkeypatch.setattr(m,"auth_owner",lambda source,hash:"synthetic-verified-owner")
    monkeypatch.setattr(m,"trusted",lambda path,**kw:Path(path).read_bytes())
    monkeypatch.setattr(m,"container_snapshot",lambda:snap)
    monkeypatch.setattr(m,"verified_main",lambda:"a"*40)
    monkeypatch.setattr(m,"replace",lambda path,data:Path(path).write_bytes(data))
    # The root-only production lock remains enforced in the actual installer.
    monkeypatch.setattr(m,"trusted_release_lock",lambda handle,path,expected_uid:True)
    class TrustedWorker:
        def _trusted_catalog_scoped_promotion_module(self,source):
            return SimpleNamespace(execute_native_catalog_scoped_request=lambda *a:None)
    mockspec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod:None))
    monkeypatch.setattr(m.importlib.util,"spec_from_file_location",lambda *a:mockspec)
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda _:TrustedWorker())
    return rootmodule,ledger,old,new


def test_exact_one_module_install_with_durable_owner_before_image(scenario):
    root,ledger,old,new=scenario
    m.execute()
    assert root.read_bytes()==new
    assert (ledger/"original-root-module.bin").read_bytes()==old
    assert m.json.loads((ledger/"owner-intent.json").read_text())["status"]=="consumed_before_mutation"
    saved=m.json.loads((ledger/"verified.json").read_text())
    assert saved["status"]=="exact_catalog_consumption_namespace_root_module_verified"
    assert saved["image_promotion"] is False and saved["provider_writes"] is False


def test_native_trusted_module_failure_restores_exact_old_bytes(scenario,monkeypatch):
    root,ledger,old,new=scenario
    class Refuse:
        def _trusted_catalog_scoped_promotion_module(self,source):
            raise PermissionError("synthetic native trusted root import failed")
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda _:Refuse())
    with pytest.raises(PermissionError,match="synthetic native"):
        m.execute()
    assert root.read_bytes()==old
    failure=m.json.loads((ledger/"failed.json").read_text())
    assert failure["status"]=="rolled_back" and failure["rollback_verified"] is True


def test_new_root_installer_never_deploys_or_restarts_pm_v4():
    code=SOURCE.read_text()
    for forbidden in (
        "docker','stop","docker','run","docker','rm",
        "systemctl','restart","systemctl','stop",
        "production-deployment-freeze.unlink"):
        assert forbidden not in code
    assert "IMAGE_PROMOTION=false; PROVIDER_WRITES=false" in code
    assert "NATIVE_LOCK" in code and "SHADOW_LOCK" in code
    assert "CATALOG_CONSUMPTION_LEDGER_REPAIR_DENIED_" in code
