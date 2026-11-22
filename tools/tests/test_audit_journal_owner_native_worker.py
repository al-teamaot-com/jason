"""Source-pinned, exact-action native archive Root-worker regression tests."""
from __future__ import annotations
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import pytest
from tools import audit_journal_owner_native_worker as root
from tools import audit_journal_owner_native_request as client

CANDIDATE="a"*40
RELEASE="release-"+CANDIDATE[:16]
POLICY={"candidate_sha":CANDIDATE,"installer_sha256":"b"*64}

def setup(tmp_path,monkeypatch):
    a=tmp_path/"authority"
    a.mkdir(mode=0o700)
    for n in ("requests","results","processed","owner-approvals","offers"):
        f=a/n;f.mkdir(mode=0o700);f.chmod(0o700)
    monkeypatch.setattr(root,"AUTH",a)
    monkeypatch.setattr(root,"REQUESTS",a/"requests")
    monkeypatch.setattr(root,"RESULTS",a/"results")
    monkeypatch.setattr(root,"PROCESSED",a/"processed")
    monkeypatch.setattr(client,"ROOT",a)
    monkeypatch.setattr(client,"WORKER",tmp_path/"root-worker")
    # Synthetic runner files are owned by the actual unprivileged test UID.
    # Production still enforces UID1000: the isolated UID0 fixture proves it.
    synthetic_uid=os.getuid()
    monkeypatch.setattr(client,"OWNER",synthetic_uid)
    original_safe_file=root.safe_file
    def synthetic_custody(path,uid,mode,maximum=30000):
        expected=synthetic_uid if uid==1000 else uid
        return original_safe_file(path,expected,mode,maximum)
    monkeypatch.setattr(root,"safe_file",synthetic_custody)
    # The synthetic preflight verifies the installed Root worker externally.
    monkeypatch.setattr(client,"available",lambda:None)
    return a

def request_bytes(request_id,action="audit_archive_stage",**overrides):
    x={"schema_version":"1.0","request_id":request_id,
       "action":action,"candidate_sha":CANDIDATE,"release_id":RELEASE}
    x.update(overrides)
    return root.canonical(x)

def write_request(folder,doc,mode=0o600):
    path=folder/"requests"/(doc["request_id"]+".json")
    path.write_bytes(root.canonical(doc))
    path.chmod(mode)
    return path

def test_read_and_dispatch_exact_unprivileged_stage_request(
        tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    record=client.submit("audit_archive_stage",CANDIDATE)
    assert record["status"]=="queued_for_exact_root_validation_not_deployed"
    assert record["owner_approval_created"] is False
    assert record["production_deployed"] is False
    request_id=record["request_id"]
    request=a/"requests"/(request_id+".json")
    parsed=root.checked_request(request,POLICY)
    assert parsed["action"]=="audit_archive_stage"
    actions=[]
    fake=SimpleNamespace(__file__="/only-reviewed-blob.py",
                         main=lambda:actions.append("reviewed-installer-stage"))
    monkeypatch.setattr(root,"exact_main_installer",
                        lambda *args:fake)
    out=root.dispatch(request,POLICY,Path("/synthetic"))
    assert out["status"]=="root_exact_owner_offer_staged"
    assert out["provider_writes"] is False
    assert actions==["reviewed-installer-stage"]

def test_adoption_requires_one_existing_exact_signed_owner_file(
        tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    with pytest.raises(FileNotFoundError):
        client.submit("audit_archive_adopt",CANDIDATE)
    path=a/"owner-approvals"/(RELEASE+".json")
    path.write_bytes(b"synthetic signed-owner-receipt")
    path.chmod(0o600)
    result=client.submit("audit_archive_adopt",CANDIDATE)
    doc=root.checked_request(
        a/"requests"/(result["request_id"]+".json"),POLICY)
    assert doc["action"]=="audit_archive_adopt"
    # The local request is NOT authority. The reviewed installer makes the
    # independent actual signature and exact-scope decision.
    actions=[]
    fake=SimpleNamespace(__file__="/only-reviewed-blob.py",
                         main=lambda:actions.append("original-root-signed-adopt"))
    monkeypatch.setattr(root,"exact_main_installer",lambda *a:fake)
    out=root.dispatch(a/"requests"/(result["request_id"]+".json"),
                      POLICY,Path("/synthetic"))
    assert out["status"]=="signed_exact_owner_root_archive_queued"
    assert actions==["original-root-signed-adopt"]

@pytest.mark.parametrize("mutation",[
    {"action":"shell"},
    {"action":"host_reconcile"},
    {"candidate_sha":"c"*40},
    {"release_id":"release-"+"c"*16},
    {"schema_version":"3.0"},
    {"approved_by":"Owner"},
])
def test_root_rejects_modified_or_foreign_request(tmp_path,monkeypatch,mutation):
    a=setup(tmp_path,monkeypatch)
    doc={"schema_version":"1.0","request_id":"c"*32,
         "action":"audit_archive_stage","candidate_sha":CANDIDATE,
         "release_id":RELEASE}
    doc.update(mutation)
    path=write_request(a,doc)
    with pytest.raises(root.NativeArchiveDenied):
        root.checked_request(path,POLICY)

@pytest.mark.parametrize("mode",[
    0o666,0o644,0o400,0o700,
])
def test_root_rejects_request_with_unsafe_mode(tmp_path,monkeypatch,mode):
    a=setup(tmp_path,monkeypatch)
    doc={"schema_version":"1.0","request_id":"c"*32,
         "action":"audit_archive_stage","candidate_sha":CANDIDATE,
         "release_id":RELEASE}
    path=write_request(a,doc,mode)
    with pytest.raises(root.NativeArchiveDenied,match="TRUSTED_FILE_CUSTODY"):
        root.checked_request(path,POLICY)

def test_root_rejects_symlink_and_hardlink(tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    doc={"schema_version":"1.0","request_id":"c"*32,
         "action":"audit_archive_stage","candidate_sha":CANDIDATE,
         "release_id":RELEASE}
    path=write_request(a,doc)
    other=a/"other";other.hardlink_to(path)
    with pytest.raises(root.NativeArchiveDenied):
        root.checked_request(path,POLICY)
    other.unlink()
    original=a/"real";path.rename(original);path.symlink_to(original)
    with pytest.raises(root.NativeArchiveDenied):
        root.checked_request(path,POLICY)

def test_wrong_producer_action_and_sha_denied(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    with pytest.raises(client.RequestDenied):
        client.submit("arbitrary_command",CANDIDATE)
    with pytest.raises(client.RequestDenied):
        client.submit("audit_archive_stage","wrong")

def test_no_root_dispatch_if_installer_source_blob_mismatches(tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    calls=[]
    def fake_git(worktree,*params,**kwargs):
        calls.append(params)
        if params[:2]==("rev-parse","HEAD"):return (CANDIDATE+"\n").encode()
        if params[0]=="status":return b""
        if params[0]=="ls-remote":return (
            CANDIDATE+"\trefs/heads/main\n").encode()
        if params[0]=="show":return b"def main():pass\n"
        raise AssertionError("unexpected Git operation")
    monkeypatch.setattr(root,"reviewed_git",fake_git)
    with pytest.raises(root.NativeArchiveDenied,match="EXACT_AUDIT_INSTALLER_HASH_CHANGED"):
        root.exact_main_installer(POLICY,a)
    assert ("show",CANDIDATE+":tools/audit_journal_install.py") in calls

def test_reviewed_source_executes_only_git_exact_blob(tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    source=b"def main():\n  return 'fixture_source_only'\n"
    policy=dict(POLICY,installer_sha256=root.sha(source))
    def fake_git(worktree,*params,**kwargs):
        if params[:2]==("rev-parse","HEAD"):return (CANDIDATE+"\n").encode()
        if params[0]=="status":return b""
        if params[0]=="ls-remote":return (
            CANDIDATE+"\trefs/heads/main\n").encode()
        if params[0]=="show":return source
        raise AssertionError("unreviewed source")
    monkeypatch.setattr(root,"reviewed_git",fake_git)
    fn=root.exact_main_installer(policy,a)
    assert fn.main()=="fixture_source_only"

def test_wrong_main_source_and_foreign_standing_auth_denied(tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(root,"reviewed_git",lambda *args,**kw:b"0"*40+b"\n")
    with pytest.raises(root.NativeArchiveDenied):
        root.exact_main_installer(POLICY,a)

def test_worker_has_no_generic_shell_execution_hook():
    source=Path(root.__file__).read_text()
    assert "shell=True" not in source
    assert "eval(" not in source
    assert "os.system(" not in source
    assert "request.get('command')" not in source
    assert "ALLOWED=frozenset" in source
    assert "EXACT_AUDIT_INSTALLER_HASH_CHANGED" in source
    assert "PROTECTED_MAIN_HAS_ADVANCED" in source


def test_request_id_path_binding_mismatch_denied(tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    doc={"schema_version":"1.0","request_id":"c"*32,
         "action":"audit_archive_stage","candidate_sha":CANDIDATE,
         "release_id":RELEASE}
    path=write_request(a,doc)
    forged=a/"requests"/("b"*32+".json")
    path.rename(forged)
    with pytest.raises(root.NativeArchiveDenied,match="REQUEST_SCHEMA_OR_SCOPE"):
        root.checked_request(forged,POLICY)


def test_drain_never_overwrites_existing_request_result(
        tmp_path,monkeypatch):
    a=setup(tmp_path,monkeypatch)
    document={
       "schema_version":"1.0","request_id":"c"*32,
       "action":"audit_archive_stage","candidate_sha":CANDIDATE,
       "release_id":RELEASE,
    }
    request=write_request(a,document)
    result=a/"results"/request.name
    result.write_bytes(b"prior protected outcome")
    result.chmod(0o600)
    monkeypatch.setattr(root,"root_stage_trust",
                        lambda:(POLICY,a))
    monkeypatch.setattr(root,"request_folders",lambda:None)
    with pytest.raises(root.NativeArchiveDenied,
                       match="PREVIOUS_ROOT_REQUEST_RESULT_ALREADY_EXISTS"):
        root.drain()
    assert request.exists() and result.read_bytes()==b"prior protected outcome"
