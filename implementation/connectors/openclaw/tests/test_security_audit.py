from __future__ import annotations

from pathlib import Path

from jason_openclaw.security_audit import SQLiteIngressSecurityAudit


def test_ingress_security_audit_is_durable_and_sanitized(tmp_path: Path):
    database = tmp_path / "ingress-audit.sqlite3"
    audit = SQLiteIngressSecurityAudit(database)
    audit.append(
        "openclaw.transport_denied",
        {
            "request_id": "req-1",
            "correlation_id": "corr-1",
            "machine_identity": "machine:openclaw-prod",
            "reason": "signature_invalid",
            "signature": "must-not-persist",
            "authorization": "must-not-persist",
            "nested": {"token": "must-not-persist", "safe": "yes"},
        },
    )
    audit.close()

    reopened = SQLiteIngressSecurityAudit(database)
    events = reopened.list_by_correlation("corr-1")
    reopened.close()

    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["reason"] == "signature_invalid"
    assert payload["nested"] == {"safe": "yes"}
    assert "signature" not in payload
    assert "authorization" not in payload
    assert database.stat().st_mode & 0o777 == 0o600
