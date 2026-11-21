"""Root spool security with disposable paths; never access production state."""
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest
from tools import owner_objective_root_worker as worker


@pytest.fixture
def queue(tmp_path, monkeypatch):
    spool, private = tmp_path / "spool", tmp_path / "private"
    spool.mkdir(mode=0o755); private.mkdir(mode=0o700)
    for name, mode in (("requests",0o700), ("results",0o755), ("processed",0o700)):
        (spool/name).mkdir(mode=mode)
    calls = []
    monkeypatch.setattr(worker, "process", lambda m,c,p: calls.append(m) or {"verified": True})
    context = (None,None,None,None,lambda x:json.dumps(x).encode())
    def submit(raw):
        identifier=sha256(raw).hexdigest()
        path=spool/"requests"/(identifier+".json")
        path.write_bytes(raw); path.chmod(0o600)
        return path
    def drain():
        return worker.drain_one({}, context, spool=spool, private=private,
            request_uid=os.geteuid(), result_uid=os.geteuid())
    return spool, private, calls, submit, drain


def test_one_request_is_archived_and_exact_replay_does_not_execute_again(queue):
    spool,_,calls,submit,drain=queue
    path=submit(b'{"operation":"test"}')
    assert drain() and not path.exists()
    assert (spool/"processed"/path.name).read_bytes()==b'{"operation":"test"}'
    submit(b'{"operation":"test"}')
    assert drain() and len(calls)==1
    assert not drain()


@pytest.mark.parametrize("raw",[b'{bad-json',b'[]',b'null'])
def test_malformed_packet_is_bounded_denial_and_does_not_poison_queue(queue,raw):
    spool,_,calls,submit,drain=queue
    path=submit(raw)
    assert drain() and not calls
    result=json.loads((spool/"results"/path.name).read_bytes())
    assert result["status"]=="denied" and result["execution_state"]=="not_started"
    assert not path.exists()


def test_prior_result_wrong_permissions_cannot_suppress_execution(queue):
    spool,_,calls,submit,drain=queue
    path=submit(b'{"operation":"test"}')
    prior=spool/"results"/path.name
    prior.write_text("{}");prior.chmod(0o666)
    with pytest.raises(PermissionError,match="FILE_IDENTITY"):
        drain()
    assert not calls and path.exists()


def test_result_symlink_cannot_write_outside_held_root_directory(queue,tmp_path):
    spool,_,calls,submit,drain=queue
    path=submit(b'{"operation":"test"}')
    victim=tmp_path/"victim";victim.write_text("preserve")
    (spool/"results"/path.name).symlink_to(victim)
    with pytest.raises(OSError):
        drain()
    assert victim.read_text()=="preserve" and not calls


def test_hardlinked_packet_is_rejected_before_processing(queue):
    spool,private,calls,submit,drain=queue
    path=submit(b'{"operation":"test"}')
    os.link(path, private/"hardlink")
    with pytest.raises(PermissionError,match="FILE_IDENTITY"):
        drain()
    assert not calls


def test_foreign_archive_is_not_accepted_as_exact_replay(queue):
    spool,_,calls,submit,drain=queue
    path=submit(b'{"operation":"test"}')
    prior=spool/"processed"/path.name
    prior.write_text("different");prior.chmod(0o400)
    with pytest.raises(PermissionError,match="ARCHIVE_CHANGED"):
        drain()
    assert path.exists()


def test_dirfd_writer_stays_with_original_directory_after_parent_rename(tmp_path):
    parent=tmp_path/"parent"; parent.mkdir()
    directory=parent/"results";directory.mkdir()
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        parent.rename(tmp_path/"before")
        parent.mkdir();(parent/"results").mkdir()
        worker.put_at(fd,"receipt.json",b"bound",0o444)
        assert (tmp_path/"before/results/receipt.json").read_bytes()==b"bound"
        assert not (parent/"results/receipt.json").exists()
    finally:
        os.close(fd)
