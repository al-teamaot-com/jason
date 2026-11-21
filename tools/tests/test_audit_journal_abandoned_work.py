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


def test_release_history_probe_requires_both_current_and_sealed_events(native):
    from tools.tests.test_audit_journal_native import event
    from orchestrator import journal_sql
    p,controller,store=native
    controller.transition(initial=True)
    controller.seal_one()
    sealed=p.artifact(p.catalog()["segments"][0])
    cold=journal_sql.dispatch("reader_probes",{"paths":[str(p.active),str(sealed)]})
    assert cold["per_source_probe_counts"]==[0,1]
    store.append_event(event("post-cutover"))
    ready=journal_sql.dispatch("reader_probes",{"paths":[str(p.active),str(sealed)]})
    assert ready["per_source_probe_counts"]==[1,1]
    assert set(ready["event_ids"])=={"before","post-cutover"}


def test_prepared_rollback_protected_until_receipt_and_recoverable_cleanup(native):
    p,controller,_=native
    controller.transition(initial=True)
    controller.seal_one()
    controller.prepare_rollback()
    prepared=list(controller.recovery().storage.glob('*.prepared.sqlite3'))
    assert len(prepared)==1
    pending=controller.cleanup_abandoned_work()
    assert pending['prepared_temporary_copies_cleaned']==0
    assert prepared[0].exists()
    controller.recovery().accept_recipe()
    controller.recovery().discard_prepared()
    cleaned=controller.cleanup_abandoned_work()
    assert cleaned['prepared_temporary_copies_cleaned']==1
    assert not prepared[0].exists()
    assert controller.cleanup_abandoned_work()['prepared_temporary_copies_cleaned']==0
