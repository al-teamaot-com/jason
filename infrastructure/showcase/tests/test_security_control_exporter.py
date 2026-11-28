import json
import sqlite3
from pathlib import Path

import security_control_exporter as exporter


def _db(path: Path) -> None:
    c = sqlite3.connect(path)
    c.execute('''create table orchestration_events (
        event_id text primary key, schema_version text not null, event_type text not null,
        execution_id text not null, correlation_id text not null, organization_id text not null,
        principal_id text not null, capability_name text not null, stage text not null,
        payload text not null, occurred_at text not null
    )''')
    rows = [
        ("1","orchestration.execution_plan.denied","denied",{"provider_invoked":False,"message":"secret ticket T123 client-999"}),
        ("2","orchestration.idempotency.deduplicated","completed",{"client_id":"client-999"}),
        ("3","orchestration.authority_context.denied","denied",{}),
        ("4","orchestration.approval.consumed","completed",{}),
        ("5","orchestration.request.terminated","denied",{"reason_codes":["client_context_required"]}),
        ("6","orchestration.request.terminated","denied",{"reason_codes":["arbitrary_sensitive_reason_T123"]}),
    ]
    for eid,event_type,stage,payload in rows:
        c.execute("insert into orchestration_events values (?,?,?,?,?,?,?,?,?,?,?)",(
            eid,"1.0",event_type,"exec","corr","aot","person-al","service.ticket.update",stage,
            json.dumps(payload),"2026-09-24T00:00:00+00:00"))
    c.commit(); c.close()


def test_security_metrics_are_aggregate_and_secret_safe(tmp_path: Path):
    db=tmp_path/'events.sqlite3'; _db(db)
    m=exporter.metrics(db)
    assert 'jason_security_control_events{control="execution_plan_denied"} 1' in m
    assert 'jason_security_control_events{control="idempotency_deduplicated"} 1' in m
    assert 'jason_security_provider_invocations_blocked 1' in m
    assert 'jason_security_request_terminations{reason="client_context_required"} 1' in m
    assert 'T123' not in m
    assert 'client-999' not in m
    assert 'person-al' not in m
    assert 'arbitrary_sensitive_reason' not in m


def test_missing_database_fails_closed_without_fake_events(tmp_path: Path):
    m=exporter.metrics(tmp_path/'missing.sqlite3')
    assert 'jason_security_control_audit_available 0' in m
    assert 'jason_security_provider_invocations_blocked 0' in m
    assert 'jason_security_control_events{' not in m


def _large_append_only_db(path: Path, *, count=10_003) -> None:
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute('''CREATE TABLE orchestration_events (
        event_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL,
        event_type TEXT NOT NULL, execution_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL, organization_id TEXT NOT NULL,
        principal_id TEXT NOT NULL, capability_name TEXT NOT NULL,
        stage TEXT NOT NULL, payload TEXT NOT NULL,
        occurred_at TEXT NOT NULL
    )''')
    rows = [
        (
            str(i), "1.0",
            "orchestration.execution_plan.denied" if i % 17 == 0
            else "orchestration.request.terminated" if i % 31 == 0
            else "orchestration.request.started",
            "exec", "corr", "aot", "person-al", "service.ticket.update",
            "denied", json.dumps({
                "provider_invoked": False,
                "reason_codes": ["client_context_required"],
                "secret": "private-ticket-T12345",
            }), "2026-10-29T12:00:00Z",
        ) for i in range(count)
    ]
    c.executemany("INSERT INTO orchestration_events VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()


def test_bounded_exact_checkpointed_projection_and_recovery(tmp_path: Path):
    db = tmp_path / "audit.sqlite3"
    state = tmp_path / "state" / "projection.json"
    _large_append_only_db(db)
    projection = exporter.SecurityAuditProjection(db, state)

    assert projection.advance(limit=1000) == 1000
    partial = projection.render()
    assert 'jason_security_control_audit_available 0' in partial
    assert 'jason_security_control_projection_complete 0' in partial
    assert 'jason_security_control_events{' not in partial
    assert 'private-ticket-' not in partial

    # The worker processes a bounded set of rows per pass and creates a
    # checkpoint without ever inserting into the audit database.
    for _ in range(20):
        if projection.complete:
            break
        assert 0 <= projection.advance(limit=1000) <= 1000
    assert projection.complete
    metrics = projection.render()
    assert 'jason_security_control_audit_available 1' in metrics
    assert 'jason_security_control_projection_complete 1' in metrics
    assert 'jason_security_control_projection_persist_ok 1' in metrics
    assert 'private-ticket-' not in metrics
    assert state.exists() and state.stat().st_mode & 0o777 == 0o600
    before = state.read_text()
    assert 'private-ticket-' not in before
    cursor = projection.cursor
    controls = projection.controls.copy()
    blocked = projection.blocked

    resumed = exporter.SecurityAuditProjection(db, state)
    assert resumed.cursor == cursor
    assert resumed.controls == controls
    assert resumed.blocked == blocked
    assert resumed.advance(limit=1000) == 0
    assert resumed.complete
    assert resumed.render() == metrics


def test_append_only_writer_can_continue_between_short_read_batches(tmp_path: Path):
    db = tmp_path / "audit.sqlite3"
    _large_append_only_db(db, count=30)
    projection = exporter.SecurityAuditProjection(db, tmp_path / "projection.json")
    assert projection.advance(limit=20) == 20
    writer = sqlite3.connect(db, timeout=0.2)
    # Bounded readers cannot monopolize the database; WAL writer proceeds.
    writer.execute(
        "INSERT INTO orchestration_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("new-event","1.0","orchestration.approval.consumed",
         "exec","corr","aot","person-al","service.ticket.update",
         "completed","{}","2026-10-29T13:00:00Z"),
    )
    writer.commit()
    writer.close()
    while not projection.complete:
        projection.advance(limit=10)
    assert projection.controls["approval_consumed"] == 1


def test_sqlite_plan_uses_existing_rowid_index_without_schema_mutation(tmp_path: Path):
    db = tmp_path / "audit.sqlite3"
    _large_append_only_db(db)
    connection = sqlite3.connect(db)
    plan = connection.execute(
        "EXPLAIN QUERY PLAN SELECT rowid,event_id,event_type,"
        " CASE WHEN event_type IN "
        " ('orchestration.execution_plan.denied','orchestration.request.terminated')"
        " THEN payload ELSE NULL END FROM orchestration_events"
        " WHERE rowid>? ORDER BY rowid LIMIT ?", (0, 100),
    ).fetchall()
    assert any("SEARCH" in str(p) and "rowid>?" in str(p) for p in plan)
    assert not any("SCAN orchestration_events" in str(p) for p in plan)
    assert not any("event_type" in index[1] for index in connection.execute(
        "PRAGMA index_list(orchestration_events)").fetchall())
    connection.close()


def test_scrape_never_touches_database_and_stale_counts_fail_closed(tmp_path: Path, monkeypatch):
    db = tmp_path / "audit.sqlite3"
    _large_append_only_db(db, count=50)
    projection = exporter.SecurityAuditProjection(db)
    projection.advance(limit=100)
    assert projection.complete
    monkeypatch.setattr(exporter, "_projection", projection)
    def never_connect():
        raise AssertionError("HTTP scrape attempted SQLite I/O")
    monkeypatch.setattr(projection, "_connect", never_connect)
    rendered = exporter.metrics(exporter.DB)
    assert 'jason_security_control_audit_available 1' in rendered
    monkeypatch.setattr(exporter.time, "monotonic", lambda: projection.last_ok + 120)
    stale = exporter.metrics(exporter.DB)
    assert 'jason_security_control_audit_available 0' in stale
    assert 'jason_security_control_events{' not in stale


def test_invalid_or_replaced_checkpoint_never_claims_success(tmp_path: Path):
    db = tmp_path / "audit.sqlite3"
    state = tmp_path / "state.json"
    _large_append_only_db(db, count=20)
    projection = exporter.SecurityAuditProjection(db, state)
    projection.advance(limit=100)
    assert projection.complete
    bad = json.loads(state.read_text())
    bad["cursor_event_hash"] = "forged"
    state.write_text(json.dumps(bad))
    restored = exporter.SecurityAuditProjection(db, state)
    assert restored.cursor == 0
    assert 'jason_security_control_audit_available 0' in restored.render()
    assert restored.advance(limit=100) == 20
    assert restored.complete
