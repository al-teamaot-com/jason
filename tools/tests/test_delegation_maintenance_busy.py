"""Bounded SQLITE_BUSY recovery must never bypass delegation/audit semantics."""
from __future__ import annotations
import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "delegation_maintenance.py"
spec = importlib.util.spec_from_file_location("delegation_maintenance_under_test", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def database(tmp_path: Path) -> Path:
    path = tmp_path / "authority.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE delegations (delegation_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE authority_audit (event_type TEXT, correlation_id TEXT, principal_id TEXT, "
            "organization_id TEXT, capability TEXT, outcome TEXT, reason_codes TEXT)"
        )
        for name, expiry in [
            ("expired", datetime.now(timezone.utc) - timedelta(minutes=10)),
            ("future", datetime.now(timezone.utc) + timedelta(days=10)),
        ]:
            con.execute(
                "INSERT INTO delegations VALUES (?, ?)",
                (name, json.dumps({
                    "status": "active", "effective_until": expiry.isoformat(),
                    "organization_id": "test-org", "capability": "safe-read",
                }))
            )
    return path


def inspect(path: Path) -> tuple[dict, list]:
    with sqlite3.connect(path) as con:
        rows = con.execute("SELECT delegation_id,payload FROM delegations").fetchall()
        audit = con.execute("SELECT * FROM authority_audit").fetchall()
    return {name: json.loads(p) for name, p in rows}, audit


def test_valid_expiry_updates_only_expired_and_emits_exactly_one_audit(tmp_path, capsys):
    path = database(tmp_path)
    assert mod.deactivate_expired(path, "svc-jason-maintenance", "fixed-id") == 0
    assert mod.deactivate_expired(path, "svc-jason-maintenance", "repeat-id") == 0
    delegations, audit = inspect(path)
    assert delegations["expired"]["status"] == "expired"
    assert delegations["future"]["status"] == "active"
    assert len(audit) == 1
    assert audit[0][1] == "fixed-id"
    outputs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [x["changed_count"] for x in outputs] == [1, 0]


def test_transient_busy_retries_without_duplicate_expiry_audit(tmp_path, capsys):
    path = database(tmp_path)
    real_connect = mod.sqlite3.connect
    calls = []
    def flaky_connect(*args, **kwargs):
        calls.append(True)
        if len(calls) <= 2:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(*args, **kwargs)
    with patch.object(mod.sqlite3, "connect", side_effect=flaky_connect), patch.object(mod.time, "sleep") as sleep:
        assert mod.deactivate_expired(path, "svc-jason-maintenance", "recovered") == 0
    assert len(calls) == 3
    assert [c.args[0] for c in sleep.call_args_list] == [1.0, 2.0]
    assert len(inspect(path)[1]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "pass"


def test_persistent_busy_raises_and_preserves_delegations(tmp_path, capsys):
    path = database(tmp_path)
    with patch.object(mod.sqlite3, "connect", side_effect=sqlite3.OperationalError("database is locked")) as conn, patch.object(mod.time, "sleep") as sleep:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            mod.deactivate_expired(path, "svc-jason-maintenance", "busy")
    assert conn.call_count == mod.SQLITE_BUSY_MAX_ATTEMPTS
    assert sleep.call_count == mod.SQLITE_BUSY_MAX_ATTEMPTS - 1
    assert capsys.readouterr().out == ""
    delegations, audit = inspect(path)
    assert delegations["expired"]["status"] == "active"
    assert not audit


def test_unrelated_sqlite_errors_fail_immediately(tmp_path):
    path = database(tmp_path)
    with patch.object(mod.sqlite3, "connect", side_effect=sqlite3.OperationalError("no such table: delegations")) as conn, patch.object(mod.time, "sleep") as sleep:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            mod.deactivate_expired(path, "svc-jason-maintenance", None)
    assert conn.call_count == 1
    sleep.assert_not_called()


def test_main_fails_closed_on_sqlite_error(tmp_path, capsys):
    path = database(tmp_path)
    with patch.object(mod.sqlite3, "connect", side_effect=sqlite3.OperationalError("database is locked")), patch.object(mod.time, "sleep"):
        with patch("sys.argv", ["delegation_maintenance.py", "--database", str(path), "deactivate-expired", "--recorded-by", "svc-jason-maintenance"]):
            assert mod.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "fail"
    assert output["error_type"] == "OperationalError"


def test_database_busy_codes_are_narrow():
    assert mod._busy_error(sqlite3.OperationalError("database is locked"))
    assert mod._busy_error(sqlite3.OperationalError("database table is locked"))
    assert not mod._busy_error(sqlite3.OperationalError("permission denied"))
    assert not mod._busy_error(sqlite3.OperationalError("disk I/O error"))


def test_busy_after_update_rolls_back_before_retry(tmp_path, capsys):
    path = database(tmp_path)
    actual_connect = sqlite3.connect
    fail_once = [True]

    class Connection(sqlite3.Connection):
        def execute(self, statement, parameters=()):
            if statement.lstrip().startswith("INSERT INTO authority_audit") and fail_once[0]:
                fail_once[0] = False
                raise sqlite3.OperationalError("database is locked")
            return super().execute(statement, parameters)

    def connect_with_factory(*args, **kwargs):
        return actual_connect(*args, factory=Connection, **kwargs)

    with patch.object(mod.sqlite3, "connect", side_effect=connect_with_factory), patch.object(mod.time, "sleep") as sleep:
        assert mod.deactivate_expired(path, "svc-jason-maintenance", "one-audit") == 0
    assert sleep.call_count == 1
    assert sleep.call_args.args == (1.0,)
    delegations, audits = inspect(path)
    assert delegations["expired"]["status"] == "expired"
    assert delegations["future"]["status"] == "active"
    assert len(audits) == 1
    assert audits[0][1] == "one-audit"
    assert json.loads(capsys.readouterr().out)["changed_count"] == 1
