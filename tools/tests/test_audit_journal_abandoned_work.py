"""Bounded disposable-work recovery; never allow cleanup to touch retained history."""
from pathlib import Path
import pytest
from tools.tests.test_audit_journal_native import native
from tools.audit_journal_control import read_control


def test_crash_left_work_is_recovered_with_exact_claim(native):
    p,controller,_=native
    job=controller._job()
    (job/"temp.tmp").write_bytes(b"disposable-only")
    assert controller.cleanup_abandoned_work()["status"]=="abandoned_claimed_temporary_work_recovered"
    assert not job.exists()
    claim=read_control(controller.private/("work-"+job.name+".json"),p.custody_uid,0o400)
    assert claim["finished"] is True
    assert controller.cleanup_abandoned_work()["status"]=="no_abandoned_work"


def test_unclaimed_directory_is_preserved(native):
    _,controller,_=native
    unclaimed=controller.work/("0"*32)
    unclaimed.mkdir()
    (unclaimed/"important").write_bytes(b"do-not-delete")
    assert controller.cleanup_abandoned_work()["status"]=="no_abandoned_work"
    assert (unclaimed/"important").read_bytes()==b"do-not-delete"


def test_claimed_work_symlink_is_rejected_without_following(native):
    _,controller,_=native
    job=controller._job()
    target=controller.work/"protected-target"
    target.mkdir()
    (target/"history").write_bytes(b"preserve")
    job.rmdir()
    job.symlink_to(target,target_is_directory=True)
    with pytest.raises((PermissionError,ValueError,RuntimeError),match="JOURNAL_WORK_CLEANUP_SCOPE"):
        controller.cleanup_abandoned_work()
    assert (target/"history").read_bytes()==b"preserve"


def test_claimed_work_identity_substitution_denied(native):
    _,controller,_=native
    job=controller._job()
    moved=controller.work/("moved-"+job.name)
    job.rename(moved)
    job.mkdir()
    (job/"new-file").write_bytes(b"do-not-delete")
    with pytest.raises((PermissionError,ValueError,RuntimeError),match="JOURNAL_WORK_DIRECTORY_CHANGED"):
        controller.cleanup_abandoned_work()
    assert (job/"new-file").read_bytes()==b"do-not-delete"
