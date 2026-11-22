"""SEC-007: exact one-use native catalog trusted-runner repair, no PMv4 changes."""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "catalog_root_trusted_runner_repair_once.py"
spec=importlib.util.spec_from_file_location("catalog_runner_guard_repair_tested",SOURCE)
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_owner_device_code_token_grant_and_exact_consent(monkeypatch):
    calls=[]
    fake=SimpleNamespace(
        TENANT="synthetic-tenant",CLIENT_ID="synthetic-client",SCOPE="synthetic-scope",
        jwt_owner=lambda token:"synthetic-authenticated-owner")
    def response(url,values):
        calls.append((url,dict(values)))
        if url.endswith("/devicecode"):
            return {"device_code":"synthetic-not-real","user_code":"synthetic",
                    "verification_uri":"https://login.microsoft.com/device",
                    "expires_in":600,"interval":5}
        return {"access_token":"never-real-token"}
    fake._form=response
    mockspec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
    monkeypatch.setattr(m.importlib.util,"spec_from_file_location",lambda *a:mockspec)
    monkeypatch.setattr(m.importlib.util,"module_from_spec",lambda *a:fake)
    monkeypatch.setattr(m.time,"sleep",lambda seconds:None)
    monkeypatch.setattr("builtins.input",lambda prompt:m.CONFIRM)
    assert m.owner_auth("a"*40,"b"*64)=="synthetic-authenticated-owner"
    assert calls[1][1]["grant_type"]=="urn:ietf:params:oauth:grant-type:device_code"
    monkeypatch.setattr("builtins.input",lambda prompt:"NO")
    with pytest.raises(PermissionError,match="EXACT_OWNER_CONSENT_MISSING"):
        m.owner_auth("a"*40,"b"*64)


@pytest.fixture
def tiny_scope(tmp_path,monkeypatch):
    worker=tmp_path/"root-worker.py"
    policy=tmp_path/"root-policy.json"
    ledger=tmp_path/"oneuse"
    worker.write_bytes(b"previous worker")
    policy.write_bytes(b'{"source_sha":"old","root_worker_sha256":"old"}\n')
    monkeypatch.setattr(m,"WORKER",worker)
    monkeypatch.setattr(m,"POLICY",policy)
    monkeypatch.setattr(m,"LEDGER",ledger)
    baseline={"jason-runtime":("a","b","c"),"jason-mcp-pilot":("d","e","f"),
              "jason-pmv4-ticket-core":("g","h","i")}
    source="f"*40
    oldworker=worker.read_bytes()
    oldpolicy=policy.read_bytes()
    newworker=b"new trusted worker"
    newpolicy=b'{"source_sha":"f","root_worker_sha256":"new"}\n'
    def fake_preflight():
        assert not ledger.exists()
        return source,oldworker,oldpolicy,newworker,newpolicy,baseline
    monkeypatch.setattr(m,"preflight",fake_preflight)
    monkeypatch.setattr(m,"owner_auth",lambda sha,digest:"synthetic-approved-owner")
    @contextmanager
    def no_locks():
        yield
    monkeypatch.setattr(m,"exclusive_locks",no_locks)
    monkeypatch.setattr(m,"read",lambda path,**k:Path(path).read_bytes())
    monkeypatch.setattr(m,"run",lambda *a,**k:(source+"\trefs/heads/main\n").encode())
    monkeypatch.setattr(m,"protected_snapshot",lambda:baseline)
    monkeypatch.setattr(m,"FREEZE_SHA256",sha256(b"fixture freeze").hexdigest())
    f=tmp_path/"freeze"
    f.write_bytes(b"fixture freeze")
    monkeypatch.setattr(m,"FREEZE",f)
    return worker,policy,ledger,oldworker,oldpolicy,newworker,newpolicy,baseline


def test_exact_two_file_scope_and_single_use(tiny_scope,monkeypatch):
    worker,policy,ledger,oldworker,oldpolicy,newworker,newpolicy,baseline=tiny_scope
    passes=[]
    monkeypatch.setattr(m,"exact_trusted_loader",lambda sha:passes.append(sha))
    m.execute()
    assert worker.read_bytes()==newworker and policy.read_bytes()==newpolicy
    assert passes==["f"*40]
    proof=json.loads((ledger/"owner-intent.json").read_text())
    assert proof["status"]=="consumed_before_mutation" and proof["action"]==m.ACTION
    assert proof["approved_scope"]["old_worker_sha256"]==sha256(oldworker).hexdigest()
    assert proof["approved_scope"]["new_worker_sha256"]==sha256(newworker).hexdigest()
    assert json.loads((ledger/"verified.json").read_text())["status"]=="exact_trusted_root_runner_guard_verified"
    assert set(p.name for p in ledger.iterdir())=={
        "previous-worker.bin","previous-policy.bin","owner-intent.json","verified.json"}


def test_exact_trust_validation_failure_rolls_back_only_two_files(tiny_scope,monkeypatch):
    worker,policy,ledger,oldworker,oldpolicy,newworker,newpolicy,baseline=tiny_scope
    monkeypatch.setattr(m,"exact_trusted_loader",lambda _:m.fail("SIMULATED_ROOT_TRUST_REJECTED"))
    with pytest.raises(PermissionError,match="SIMULATED_ROOT_TRUST_REJECTED"):
        m.execute()
    assert worker.read_bytes()==oldworker and policy.read_bytes()==oldpolicy
    failed=json.loads((ledger/"failed.json").read_text())
    assert failed["status"]=="rolled_back" and failed["rollback_verified"] is True
    assert not (ledger/"verified.json").exists()


def test_owner_scope_is_not_provider_or_image_release():
    source=SOURCE.read_text()
    assert 'IMAGE_PROMOTION_APPROVED=false; PROVIDER_WRITES_APPROVED=false' in source
    assert 'CATALOG_TRUSTED_ROOT_RUNNER_GUARD_VERIFIED' in source
    assert 'old["source_sha"]' not in source or 'root_worker_sha256' in source
    for forbidden in ("docker run","docker stop","systemctl restart",
                      "systemctl stop","production-deployment-freeze.unlink"):
        assert forbidden not in source


def test_prior_root_owner_receipts_read_from_ledger_directory_not_worker_bytes():
    source=SOURCE.read_text()
    assert 'previously=Path("/var/lib/jason-catalog-scoped-promotion/rebind-ledger")' in source
    assert 'read(previously/"verified.json"' in source
    assert 'read(previously/"owner-intent.json"' in source
    assert 'read(previous/"verified.json"' not in source
    assert 'read(previous/"owner-intent.json"' not in source
