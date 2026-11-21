"""Production journal code exercised only on disposable fixture data."""
import json
import os
from pathlib import Path
import sqlite3
from dataclasses import replace
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from orchestrator.event_store import SQLiteOrchestrationEventStore,OrchestrationEvent
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore,JournalUnavailable
from orchestrator import journal_sql
from tools.audit_journal_control import JournalController,FIXTURE,atomic,require_no_handles


def event(identifier,execution="one",kind="test.observer",stage="observed",payload=None):
    return OrchestrationEvent(event_id=identifier,event_type=kind,execution_id=execution,
        correlation_id="correlation",organization_id="fixture",principal_id="fixture",
        capability_name="fixture.read",stage=stage,payload=payload or {"fixture":True})


@pytest.fixture
def native(tmp_path):
    uid=os.geteuid()
    for name in ("control","archive","pending","private","work","local"):
        path=tmp_path/name;path.mkdir(mode=0o700);os.chown(path,uid,uid)
    (tmp_path/"fixture.json").write_text(json.dumps({"format":FIXTURE}))
    active=tmp_path/"active.sqlite3"
    old=SQLiteOrchestrationEventStore(active)
    old.append_event(event("before"));old.close()
    os.chown(active,uid,uid)
    gate=tmp_path/"control/handoff.lock";gate.touch();gate.chmod(0o644);os.chown(gate,uid,uid)
    p=JournalProfile(active=active,control=tmp_path/"control",archives=tmp_path/"archive",
        pending=tmp_path/"pending",custody_uid=uid,writer_uid=uid,fixture=True)
    atomic(p.control/"catalog.json",{"schema_version":"1.0","mode":"legacy","generation":0,
        "epoch":None,"segments":[]},owner=uid)
    controller=JournalController(p,tmp_path/"private",tmp_path/"work",tmp_path/"local",fixture=True)
    store=SegmentedOrchestrationEventStore(p)
    yield p,controller,store
    store.close()


def test_handoff_archive_read_and_duplicate(native):
    p,c,s=native
    c.transition(initial=True)
    s.append_event(event("after"))
    assert s.get("before").event_id=="before"
    assert s.get("after").event_id=="after"
    result=c.seal_one();assert result["status"]=="sealed"
    assert len(s.list_by_correlation("correlation"))==2
    with pytest.raises(JournalUnavailable,match="ALREADY_EXISTS"):s.append_event(event("before"))
    assert c.status()["sealed"]==1


@pytest.mark.parametrize("point",["transition_intent","transition_preserved","transition_new_active","transition_published"])
def test_cutover_crash_recovered(native,point):
    p,c,s=native
    def fault(at):
        if at==point:raise RuntimeError("simulated-crash")
    c.fault=fault
    with pytest.raises(RuntimeError,match="simulated-crash"):c.transition(initial=True)
    if point!="transition_published":
        with pytest.raises(JournalUnavailable):s.get("before")
    else:assert s.get("before").event_id=="before"
    c.fault=lambda _:None
    assert c.recover()["status"]=="transition_recovered"
    assert s.get("before").event_id=="before"
    s.append_event(event("after"))
    assert len(s.list_by_correlation("correlation"))==2


def test_repeated_rollover_and_bounded_cache(native):
    p,c,s=native;c.transition(initial=True)
    expected={"before"}
    for i in range(5):
        s.append_event(event(str(i)));expected.add(str(i))
        c.seal_one();c.transition()
    c.seal_one()
    assert {v.event_id for v in s.list_by_execution("one")}==expected
    assert len(s._cache)<=p.cached_archives


def test_multiwriter_and_read_during_rollover(native):
    p,c,s=native;c.transition(initial=True)
    def write(index):
        local=SegmentedOrchestrationEventStore(p)
        try:
            for n in range(20):local.append_event(event(f"{index}-{n}",execution=str(index)))
        finally:local.close()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures=[pool.submit(write,i) for i in range(4)]
        rollover=pool.submit(c.transition)
        for f in futures:f.result()
        rollover.result()
    assert len(s.list_by_correlation("correlation"))==81


def test_corrupt_archive_custody_denies(native):
    p,c,s=native;c.transition(initial=True);c.seal_one()
    catalog=p.catalog();path=p.artifact(catalog["segments"][0])
    path.chmod(0o600)
    with pytest.raises(JournalUnavailable,match="CUSTODY"):s.get("before")


def test_bloom_has_no_false_negatives(native):
    p,c,s=native;c.transition(initial=True)
    for i in range(100):s.append_event(event(str(i),execution="group-"+str(i%7)))
    c.seal_one();c.transition();c.seal_one()
    assert all(s.get(str(i)) is not None for i in range(100))
    assert len(s.list_by_execution("group-0"))==15


def test_capacity_reservations_and_terminal_release(native):
    p,c,s=native;c.transition(initial=True)
    s.append_event(event("received",kind="orchestration.request.received",stage="received"))
    assert len(journal_sql.active_state(p.active)["reservations"])==1
    s.append_event(event("done",kind="orchestration.capability.completed",stage="completed"))
    assert journal_sql.active_state(p.active)["reservations"]==[]


def test_maintenance_blocks_new_admission_allows_outcome(native):
    p,c,s=native
    journal_sql.admission_barrier(p.active,True)
    with pytest.raises(JournalUnavailable,match="MAINTENANCE"):
        s.append_event(event("blocked",kind="orchestration.request.received"))
    s.append_event(event("outcome",kind="orchestration.capability.completed"))
    journal_sql.admission_barrier(p.active,False)
    s.append_event(event("unblocked",kind="orchestration.request.received"))


def test_rollback_preserves_events_after_snapshot(native):
    p,c,s=native;c.transition(initial=True);c.seal_one()
    s.append_event(event("after"))
    c.prepare_rollback()
    s.append_event(event("late"))
    c.finish_rollback()
    old=SQLiteOrchestrationEventStore(p.active)
    try:assert {e.event_id for e in old.list_by_correlation("correlation")}=={"before","after","late"}
    finally:old.close()


@pytest.mark.parametrize("point",["rollback_intent","rollback_preserved","rollback_swapped","rollback_published"])
def test_rollback_crash_preserves_tail(native,point):
    p,c,s=native;c.transition(initial=True);c.seal_one();s.append_event(event("after"))
    c.prepare_rollback();s.append_event(event("late"))
    def fault(at):
        if at==point:raise RuntimeError("simulated-crash")
    c.fault=fault
    with pytest.raises(RuntimeError,match="simulated-crash"):c.finish_rollback()
    c.fault=lambda _:None;c.recover()
    assert {e.event_id for e in s.list_by_correlation("correlation")}=={"before","after","late"}


def test_root_controller_refuses_mutable_checkout():
    from tools.audit_journal_control import root_controller
    with pytest.raises(JournalUnavailable,match="INSTALLED_ISOLATED_ROOT"):root_controller()


def test_live_legacy_connection_blocks_cutover(native):
    p,c,s=native
    connection=sqlite3.connect(p.active);connection.execute("SELECT count(*) FROM orchestration_events").fetchone()
    try:
        with pytest.raises(JournalUnavailable,match="HANDLE_STILL_OPEN"):c.transition(initial=True)
    finally:connection.close()

def test_reclaim_requires_verified_rollback_and_preserves_archive(native):
    p,c,s=native;c.transition(initial=True);c.seal_one()
    identifier=p.catalog()["segments"][0]["id"]
    with pytest.raises(FileNotFoundError):c.reclaim(identifier)
    c.prepare_rollback();c.reclaim(identifier)
    assert s.get("before").event_id=="before"
    s.append_event(event("new"))
    c.finish_rollback()
    assert {e.event_id for e in s.list_by_execution("one")}=={"before","new"}


def test_existing_provider_work_may_finish_during_admission_pause(native):
    p,c,s=native
    journal_sql.admission_barrier(p.active,True)
    s.append_event(event("already-admitted",kind="orchestration.capability.invoking"))
    s.append_event(event("outcome",kind="orchestration.capability.completed"))


@pytest.mark.parametrize("kind",["orchestration.request.terminated","orchestration.check_only.validated",
                               "orchestration.execution_plan.denied"])
def test_all_terminal_paths_release_reserve(native,kind):
    p,c,s=native;c.transition(initial=True)
    s.append_event(event("receive",kind="orchestration.request.received"))
    s.append_event(event("terminal",kind=kind,stage="denied"))
    assert journal_sql.active_state(p.active)["reservations"]==[]


def test_outsized_metadata_is_rejected_before_append(native):
    p,c,s=native
    with pytest.raises(JournalUnavailable,match="METADATA_TOO_LARGE"):s.append_event(event("x"*513))
    assert len(s.list_by_execution("one"))==1


def test_bloom_corruption_detected_before_publication(native,tmp_path):
    p,c,s=native
    directory=tmp_path/"filters";directory.mkdir()
    records=journal_sql.filters(p.active,directory,"test",1)
    item=records["event_id"];path=directory/item["file"]
    path.write_bytes(bytes(path.stat().st_size))
    item["sha256"]=journal_sql.file_hash(path)
    with pytest.raises(JournalUnavailable,match="FALSE_NEGATIVE"):
        journal_sql.validate_filters(p.active,directory,records)
