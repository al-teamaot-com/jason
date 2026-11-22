"""Disposable migration contracts; never mount or open production state."""
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context
from pathlib import Path
import json
import os
import sqlite3
import threading
import time

import pytest

from tools.audit_journal_migration import Workspace, Migration, content_proof, database, rehearsal
from orchestrator.event_store import OrchestrationEvent, SQLiteOrchestrationEventStore

NOW=datetime(2026,11,21,tzinfo=timezone.utc)


def event(identifier, *, sequence=0):
    return OrchestrationEvent(event_id=identifier,event_type="synthetic.event",
        execution_id="same-execution",correlation_id="same-correlation",organization_id="aot",
        principal_id="synthetic",capability_name="synthetic.audit",stage="recorded",
        occurred_at=NOW+timedelta(seconds=sequence),payload={"sequence":sequence})


@pytest.fixture
def case(tmp_path):
    w=Workspace.create(tmp_path/"work")
    return w,Migration(w)


def test_end_to_end_rehearsal_never_reports_production_readiness(tmp_path):
    result=rehearsal(tmp_path/"work")
    assert result["events_preserved"]==4 and result["production_data_accessed"] is False
    assert result["production_ready"] is False


def test_cross_day_execution_and_correlation_keep_order_and_old_lookup(case):
    w,m=case
    w.append_event(event("old",sequence=1));m.cutover_or_rotate()
    w.append_event(event("new",sequence=2));m.seal_pending()
    m.cutover_or_rotate();w.append_event(event("latest",sequence=3));m.seal_pending()
    assert [e.event_id for e in w.list_by_execution("same-execution")]==["old","new","latest"]
    assert [e.event_id for e in w.list_by_correlation("same-correlation")]==["old","new","latest"]
    assert w.get("old").payload["sequence"]==1 and w.get("missing") is None


def test_duplicate_event_is_denied_across_sealed_and_active_history(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();m.seal_pending()
    with pytest.raises(RuntimeError,match="ALREADY_EXISTS"):w.append_event(event("old"))
    assert len(w.list_by_execution("same-execution"))==1


def writer(root,prefix,count):
    w=Workspace(root)
    for i in range(count):w.append_event(event(prefix+str(i),sequence=i))


def test_real_process_writers_and_rotation_have_no_lost_or_duplicated_commits(case):
    w,m=case
    ctx=get_context("spawn")
    children=[ctx.Process(target=writer,args=(str(w.root),prefix,35)) for prefix in ("a","b")]
    for child in children:child.start()
    for _ in range(3):
        m.cutover_or_rotate();time.sleep(0.03)
    for child in children:
        child.join(20);assert child.exitcode==0
    m.seal_pending()
    observed=w.list_by_execution("same-execution")
    assert len(observed)==70 and len({e.event_id for e in observed})==70


@pytest.mark.parametrize("boundary",["intent","renamed","new_active","published"])
def test_interrupted_cutover_recovers_without_loss_or_another_rotation(case,boundary):
    w,m=case
    w.append_event(event("old"))
    def crash(stage):
        if stage==boundary:raise SystemExit("simulated stop")
    m.fault=crash
    with pytest.raises(SystemExit):m.cutover_or_rotate()
    with pytest.raises(RuntimeError,match="RECOVERY_REQUIRED"):w.append_event(event("new"))
    m.recover();m.recover()
    w.append_event(event("new",sequence=1))
    assert len(w.state()["segments"])==1
    assert {e.event_id for e in w.list_by_execution("same-execution")}=={"old","new"}


@pytest.mark.parametrize("boundary",["rollback_intent","rollback_preserved","rollback_swapped","rollback_published"])
def test_interrupted_rollback_recovers_without_discarding_new_commits(case,boundary):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();w.append_event(event("new",sequence=1))
    plan=m.prepare_rollback();w.append_event(event("tail",sequence=2))
    def crash(stage):
        if stage==boundary:raise SystemExit("simulated stop")
    m.fault=crash
    with pytest.raises(SystemExit):m.finish_rollback(plan)
    with pytest.raises(RuntimeError,match="RECOVERY_REQUIRED"):w.append_event(event("later"))
    m.recover();m.recover()
    assert w.state()["mode"]=="legacy"
    original=SQLiteOrchestrationEventStore(w.root/"live.sqlite3")
    try:
        assert {e.event_id for e in original.list_by_execution("same-execution")}=={"old","new","tail"}
    finally:original.close()


def test_rollback_rebuilds_when_archive_generation_changes_and_preserves_all_events(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate()
    first=m.prepare_rollback()
    w.append_event(event("tail"));m.cutover_or_rotate()
    with pytest.raises(RuntimeError,match="REBUILD_REQUIRED"):m.finish_rollback(first)
    assert {e.event_id for e in w.list_by_execution("same-execution")}=={"old","tail"}
    m.finish_rollback(m.prepare_rollback())
    assert content_proof(w.root/"live.sqlite3")["events"]==2


@pytest.mark.parametrize("change",["missing","tampered"])
def test_bad_archive_denies_historical_read_without_false_empty_success(case,change):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();m.seal_pending()
    path=w.path(w.state()["segments"][0]["path"])
    if change=="missing":path.unlink()
    else:
        path.chmod(0o600)
        with path.open("ab") as stream:stream.write(b"altered")
    with pytest.raises((FileNotFoundError,RuntimeError)):w.list_by_execution("same-execution")


def test_archive_copy_or_verification_failure_retains_original_history(case,monkeypatch):
    from tools import audit_journal_migration as module
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate()
    original=module.content_proof
    def fail(path):
        if path.suffix==".staging":raise RuntimeError("simulated bad copy")
        return original(path)
    monkeypatch.setattr(module,"content_proof",fail)
    with pytest.raises(RuntimeError,match="bad copy"):m.seal_pending()
    assert w.state()["segments"][0]["state"]=="pending"
    assert w.get("old") is not None


def test_nonempty_workspace_and_path_escape_are_denied(case,tmp_path):
    w,m=case
    with pytest.raises(RuntimeError,match="EMPTY_WORKSPACE"):Workspace.create(w.root)
    for path in ("../escape","/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3"):
        with pytest.raises(RuntimeError):w.path(path)
    (w.root/"pending/link").symlink_to(tmp_path)
    with pytest.raises(RuntimeError,match="LINKED_WORKSPACE_PATH"):w.path("pending/link/escape")


def test_original_legacy_api_reads_rollback_output_including_post_preparation_events(case):
    w,m=case
    for i in range(10):w.append_event(event("old-"+str(i),sequence=i))
    m.cutover_or_rotate();m.seal_pending()
    plan=m.prepare_rollback()
    for i in range(10):w.append_event(event("tail-"+str(i),sequence=i+10))
    assert m.finish_rollback(plan)["events"]==20
    legacy=SQLiteOrchestrationEventStore(w.root/"live.sqlite3")
    try:assert len(legacy.list_by_execution("same-execution"))==20
    finally:legacy.close()


def test_archive_is_standalone_without_wal_and_reclaims_only_after_verified_copy(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();m.seal_pending()
    segment=w.state()["segments"][0];path=w.path(segment["path"])
    with database(path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0]=="delete"
    assert not Path(str(path)+"-wal").exists()
    with pytest.raises(RuntimeError,match="COPY_RECEIPT_REQUIRED"):
        m.reclaim_synthetic_before_image(segment["id"],{})
    assert w.path(segment["before_image_path"]).exists()
    copy=m.secondary_copy(segment["id"])
    assert copy["independent_backup_verified"] is False
    m.reclaim_synthetic_before_image(segment["id"],copy)
    m.reclaim_synthetic_before_image(segment["id"],copy)
    assert not w.path(segment["before_image_path"]).exists()
    w.append_event(event("new",sequence=1))
    m.finish_rollback(m.prepare_rollback())
    assert {e.event_id for e in w.list_by_execution("same-execution")}=={"old","new"}


def test_bad_second_copy_cannot_authorize_before_image_reclamation(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();m.seal_pending()
    segment=w.state()["segments"][0]
    copy=m.secondary_copy(segment["id"])
    p=w.path(copy["path"]);p.chmod(0o600);p.write_bytes(b"bad")
    with pytest.raises(RuntimeError,match="COPIES_REQUIRED"):
        m.reclaim_synthetic_before_image(segment["id"],copy)
    assert w.path(segment["before_image_path"]).exists()
    assert w.get("old") is not None


@pytest.mark.parametrize("opened,now,expected",[
    ("2026-11-20T05:20:00+00:00","2026-11-21T05:14:00+00:00",None),
    ("2026-11-20T05:20:00+00:00","2026-11-21T05:15:00+00:00","daily"),
    ("2026-10-31T04:20:00+00:00","2026-11-01T04:15:00+00:00","daily"),
    ("2026-11-01T04:20:00+00:00","2026-11-02T05:15:00+00:00","daily"),
    ("2026-03-08T05:20:00+00:00","2026-03-09T04:15:00+00:00","daily"),
])
def test_daily_boundary_handles_local_midnight_and_daylight_saving(opened,now,expected):
    from tools.audit_journal_migration import rollover_reason
    assert rollover_reason(opened_at=datetime.fromisoformat(opened),now=datetime.fromisoformat(now),
        active_bytes=1)==expected


def test_size_limit_and_emergency_ceiling_do_not_wait_for_next_midnight():
    from tools.audit_journal_migration import rollover_reason
    assert rollover_reason(opened_at=NOW,now=NOW,active_bytes=1073741824)=="size"
    assert rollover_reason(opened_at=NOW,now=NOW,active_bytes=2147483648)=="admission_ceiling"
    with pytest.raises(RuntimeError,match="MONOTONIC_TIME"):
        rollover_reason(opened_at=NOW,now=NOW-timedelta(seconds=1),active_bytes=1)


def test_interrupted_archive_publication_recovers_by_content_readback(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate()
    def crash(stage):
        if stage=="archive_verified_before_catalog":raise SystemExit("stop after copy")
    m.fault=crash
    with pytest.raises(SystemExit):m.seal_pending()
    assert w.state()["segments"][0]["state"]=="pending"
    m.fault=lambda _:None
    m.seal_pending()
    assert w.state()["segments"][0]["state"]=="sealed" and w.get("old") is not None


def test_rollback_recovery_rejects_changed_published_target(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate()
    plan=m.prepare_rollback();w.append_event(event("tail"))
    def crash(stage):
        if stage=="rollback_swapped":raise SystemExit("stop after swap")
    m.fault=crash
    with pytest.raises(SystemExit):m.finish_rollback(plan)
    with (w.root/"live.sqlite3").open("ab") as stream:stream.write(b"tampered")
    with pytest.raises(RuntimeError,match="CONTENT_MISMATCH"):m.recover()
    assert w.transaction.exists()


def test_uncoordinated_legacy_connection_denies_cutover_before_mutation(case):
    w,m=case
    old=SQLiteOrchestrationEventStore(w.root/"live.sqlite3")
    try:
        old.append_event(event("legacy"))
        with pytest.raises(RuntimeError,match="CONNECTION_STILL_OPEN"):m.cutover_or_rotate()
        assert w.state()["mode"]=="legacy" and not w.transaction.exists()
    finally:old.close()
    m.cutover_or_rotate()
    assert w.get("legacy") is not None


def test_corrupt_archive_also_denies_new_append_and_rollback_preparation(case):
    w,m=case
    w.append_event(event("old"));m.cutover_or_rotate();m.seal_pending()
    path=w.path(w.state()["segments"][0]["path"]);path.chmod(0o600)
    with path.open("ab") as stream:stream.write(b"tampered")
    with pytest.raises(RuntimeError,match="HASH_MISMATCH"):w.append_event(event("new"))
    with pytest.raises(RuntimeError,match="HASH_MISMATCH"):m.prepare_rollback()
    with database(w.root/"live.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()[0]==0
