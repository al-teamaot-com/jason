"""Closed historical SQLite segments may not leave live readers behind.

This reproduces the protected Root maintenance gate's requirement that no
process holds the sealed history after a completed query, including failures.
Fixtures never reference production paths or provider tools.
"""
import os
from pathlib import Path
import pytest
import sqlite3
from tools.tests.test_audit_journal_native import native, event


def process_handles_for(path):
    target=Path(path).stat()
    matches=[]
    for name in os.listdir("/proc/self/fd"):
        fd=Path("/proc/self/fd")/name
        try:
            info=fd.stat()
        except (FileNotFoundError,ProcessLookupError):
            continue
        if (info.st_dev,info.st_ino)==(target.st_dev,target.st_ino):
            matches.append(name)
    return matches


def test_query_closes_sealed_historical_connection_before_return(native):
    profile,controller,reader=native
    controller.transition(initial=True)
    controller.seal_one()
    historic=profile.artifact(profile.catalog()["segments"][0])
    assert not process_handles_for(historic)
    for i in range(3):
        assert reader.get("before").event_id=="before"
        assert not process_handles_for(historic),f"persisting read after pass {i}"
        assert not any(isinstance(v,sqlite3.Connection) for v in reader._cache.values())
    # Root's unmodified guard must accept the sealed segment after query.
    from tools.audit_journal_control import require_no_handles
    require_no_handles(historic)


def test_exception_does_not_retain_sealed_archive_file_descriptor(native):
    profile,controller,reader=native
    controller.transition(initial=True)
    controller.seal_one()
    rec=profile.catalog()["segments"][0]
    historic=profile.artifact(rec)
    with pytest.raises(RuntimeError,match="simulated"):
        with reader._archive_query(rec,"SELECT * FROM orchestration_events WHERE event_id=?",("before",)) as rows:
            assert rows.fetchone()["event_id"]=="before"
            raise RuntimeError("simulated")
    assert not process_handles_for(historic)
    assert reader.get("before").event_id=="before"
    assert not process_handles_for(historic)


def test_archive_reads_release_handles_across_rotations(native):
    profile,controller,reader=native
    controller.transition(initial=True)
    for i in range(3):
        reader.append_event(event(str(i)))
        controller.seal_one()
        assert reader.list_by_execution("one")
        for rec in profile.catalog()["segments"]:
            assert not process_handles_for(profile.artifact(rec))
        if i<2:controller.transition()
    assert not any(isinstance(v,sqlite3.Connection) for v in reader._cache.values())
