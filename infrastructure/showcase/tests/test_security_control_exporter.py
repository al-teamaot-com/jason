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
