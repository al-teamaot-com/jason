from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger


def test_consumed_approval_is_not_deleted_after_expiry(tmp_path):
    now = [datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)]
    path = tmp_path / "governed.sqlite3"
    ledger = SQLiteGovernedExecutionLedger(str(path), clock=lambda: now[0])
    ledger.initialize()
    arguments = {"payload": {"id": 143589, "status": "In Progress"}}

    first = ledger.reserve_approval(
        principal_id="jason-autonomy-worker",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.update",
        arguments=arguments,
        request_id="exec-1",
        ttl_seconds=60,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE governed_action_approvals "
            "SET state='consumed', execution_id='exec-1', correlation_id='corr-1' "
            "WHERE approval_id=?",
            (first.approval_id,),
        )

    now[0] += timedelta(minutes=10)
    second = ledger.reserve_approval(
        principal_id="jason-autonomy-worker",
        organization_id="aot",
        client_id=None,
        capability_name="service.ticket.update",
        arguments=arguments,
        request_id="exec-2",
        ttl_seconds=60,
    )

    assert second.approval_id == first.approval_id
    assert second.idempotency_key == first.idempotency_key
    assert second.created is False
    evidence = ledger.evidence(first.approval_id)
    assert evidence is not None
    assert evidence["state"] == "consumed"
    assert evidence["request_id"] == "exec-1"
