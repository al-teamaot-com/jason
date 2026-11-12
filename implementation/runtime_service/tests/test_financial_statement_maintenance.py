from __future__ import annotations

from datetime import datetime, timezone

import jason_runtime.financial_statement_maintenance as mod
from jason_runtime.financial_statement_maintenance import (
    FinancialStatementMaintenance,
    SQLiteFinancialStatementState,
    classify_statement,
)


def test_classify_known_bank_statement_uses_verified_folder_mapping():
    identity = classify_statement(
        "Atlantic Union Bank\nAccount ending in 3049\nStatement Period 10/01/2026\n"
    )
    assert identity is not None
    assert identity.filename == "AtlanticUnionBank-3049-102026.pdf"
    assert identity.account_label == "Checking 3049"


def test_classify_truist_line_of_credit_uses_existing_account_folder():
    identity = classify_statement(
        "Truist\nLine of Credit account ending in 7788\nStatement Date: 10/31/2026\n"
    )
    assert identity is not None
    assert identity.account_label == "Line of Credit"
    assert identity.filename == "Truist-7788-102026.pdf"


def test_non_statement_is_not_classified():
    assert classify_statement(
        "Atlantic Union Bank payroll approval report account ending in 3049 Statement Date 10/31/2026"
    ) is None


class FakeAudit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeSharePoint:
    def __init__(self):
        self.items = {
            "root": {"id": "root", "name": "Bank Checking Accounts Register", "folder": {}},
            "drop": {"id": "drop", "name": "Bank statment", "folder": {}, "parentReference": {"id": "root"}},
            "canonical": {"id": "canonical", "name": "Bank Statements - Organized", "folder": {}, "parentReference": {"id": "root"}},
            "file1": {"id": "file1", "name": "random.pdf", "file": {}, "parentReference": {"id": "drop"}},
            "unrelated": {"id": "unrelated", "name": "invoice.pdf", "file": {}, "parentReference": {"id": "drop"}},
        }
        self.children = {"root": ["drop", "canonical"], "drop": ["file1", "unrelated"], "canonical": []}
        self.data = {
            "file1": b"Atlantic Union Bank\nAccount ending in 3049\nStatement Period 10/01/2026\n",
            "unrelated": b"Atlantic Union Bank invoice account ending in 3049 Statement Period 10/01/2026",
        }
        self.created = 0
        self.moves = []

    def get_item_by_path(self, **kwargs):
        return dict(self.items["root"])

    def list_children(self, *, item_id, **kwargs):
        return tuple(dict(self.items[x]) for x in self.children.get(item_id, []))

    def download_file(self, *, item_id, **kwargs):
        return self.data[item_id]

    def create_folder(self, *, parent_id, name, **kwargs):
        self.created += 1
        item_id = f"folder{self.created}"
        self.items[item_id] = {"id": item_id, "name": name, "folder": {}, "parentReference": {"id": parent_id}}
        self.children.setdefault(parent_id, []).append(item_id)
        self.children[item_id] = []
        return dict(self.items[item_id])

    def move_and_rename(self, *, item_id, destination_parent_id, new_name, **kwargs):
        prior = self.items[item_id]["parentReference"]["id"]
        self.children[prior].remove(item_id)
        self.children.setdefault(destination_parent_id, []).append(item_id)
        self.items[item_id]["parentReference"] = {"id": destination_parent_id}
        self.items[item_id]["name"] = new_name
        self.moves.append((item_id, destination_parent_id, new_name))
        return dict(self.items[item_id])

    def get_item(self, *, item_id, **kwargs):
        return dict(self.items[item_id])


def test_daily_run_moves_verified_statement_and_second_run_is_idempotent(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    state = SQLiteFinancialStatementState(tmp_path / "state.sqlite3")
    times = iter([
        datetime(2026, 11, 5, 10, 5, tzinfo=timezone.utc),
        datetime(2026, 11, 5, 10, 6, tzinfo=timezone.utc),
        datetime(2026, 11, 5, 10, 7, tzinfo=timezone.utc),
        datetime(2026, 11, 5, 10, 8, tzinfo=timezone.utc),
    ])
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive", audit=FakeAudit(),
        now=lambda: next(times),
    )
    first = worker.run_once(now=datetime(2026, 11, 5, 10, 5, tzinfo=timezone.utc))
    assert first["moved"] == 1
    assert first["ambiguous_or_unclassified"] == 1
    assert client.moves[0][2] == "AtlanticUnionBank-3049-102026.pdf"
    second = worker.run_once(now=datetime(2026, 11, 5, 10, 7, tzinfo=timezone.utc))
    assert second["moved"] == 0
    assert second["already_canonical"] == 1


def test_tick_waits_until_0500_eastern_and_runs_once(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    state = SQLiteFinancialStatementState(tmp_path / "state.sqlite3")
    clock = [datetime(2026, 11, 5, 9, 59, tzinfo=timezone.utc)]  # 04:59 EST
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive", audit=FakeAudit(), now=lambda: clock[0]
    )
    assert worker.tick() is False
    clock[0] = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)  # 05:00 EST
    assert worker.tick() is True
    assert worker.tick() is False


def test_partial_run_is_not_marked_complete_and_retries_after_15_minutes(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    original_move = client.move_and_rename
    failures = {"remaining": 1}
    def flaky_move(**kwargs):
        if failures["remaining"]:
            failures["remaining"] -= 1
            raise RuntimeError("controlled move failure")
        return original_move(**kwargs)
    client.move_and_rename = flaky_move
    state = SQLiteFinancialStatementState(tmp_path / "state.sqlite3")
    clock = [datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)]
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive", audit=FakeAudit(), now=lambda: clock[0]
    )
    assert worker.tick() is True
    assert state.completed("2026-11-05") is False
    clock[0] = datetime(2026, 11, 5, 10, 10, tzinfo=timezone.utc)
    assert worker.tick() is False
    clock[0] = datetime(2026, 11, 5, 10, 15, tzinfo=timezone.utc)
    assert worker.tick() is True
    assert state.completed("2026-11-05") is True


def test_statement_period_range_uses_closing_month():
    identity = classify_statement(
        "PNC Bank\nAccount ending in 5842\nStatement Period 09/30/2026 - 10/30/2026\n"
    )
    assert identity is not None
    assert identity.filename == "PNCBank-5842-102026.pdf"


def test_audit_event_chain_preserves_retry_history_and_detects_tampering(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    state = SQLiteFinancialStatementState(tmp_path / "audit.sqlite3")
    clock = [datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)]
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive", audit=FakeAudit(), now=lambda: clock[0]
    )
    original_move = client.move_and_rename
    fail_once = [True]

    def fail_then_move(**kwargs):
        if fail_once[0]:
            fail_once[0] = False
            raise RuntimeError("controlled provider rejection")
        return original_move(**kwargs)

    client.move_and_rename = fail_then_move
    assert worker.tick() is True
    assert state.completed("2026-11-05") is False
    clock[0] = datetime(2026, 11, 5, 10, 15, tzinfo=timezone.utc)
    assert worker.tick() is True
    assert state.completed("2026-11-05") is True
    events = [x[0] for x in state.db.execute(
        "SELECT event_type FROM financial_statement_events ORDER BY event_id"
    )]
    assert events.count("run_started") == 2
    assert events.count("run_finished") == 2
    assert events.count("move_intent") == 2
    assert events.count("file_error") == 1
    assert events.count("move_verified") == 1
    assert state.verify_event_chain() is True
    # These events live in an independent table, not the replaceable run summary.
    state.db.execute(
        "UPDATE financial_statement_events SET metadata_json=? WHERE event_type='file_error'",
        ('{"error":"fabricated"}',),
    )
    assert state.verify_event_chain() is False


def test_audit_write_failure_prevents_sharepoint_mutation(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    state = SQLiteFinancialStatementState(tmp_path / "audit.sqlite3")
    now = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
    original = state.event

    def reject_intent(date, when, kind, metadata):
        if kind == "move_intent":
            raise RuntimeError("audit ledger unavailable")
        return original(date, when, kind, metadata)

    monkeypatch.setattr(state, "event", reject_intent)
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive", audit=FakeAudit(), now=lambda: now
    )
    summary = worker.run_once(now=now)
    assert summary["success"] is False
    assert summary["moved"] == 0
    assert client.moves == []
    assert state.verify_event_chain() is True


def test_canonical_audit_persists_intent_before_any_sharepoint_move(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    audit = FakeAudit()
    state = SQLiteFinancialStatementState(tmp_path / "audit.sqlite3")
    now = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive",
        audit=audit, now=lambda: now,
    )
    original_move = client.move_and_rename

    def verified_prewrite(**kwargs):
        assert any(e[0] == "financial.statement.move_intent" for e in audit.events)
        return original_move(**kwargs)

    client.move_and_rename = verified_prewrite
    assert worker.run_once(now=now)["moved"] == 1
    assert any(e[0] == "financial.statement.move_verified" for e in audit.events)
    assert state.verify_event_chain()


def test_canonical_audit_failure_blocks_sharepoint_move(tmp_path, monkeypatch):
    client = FakeSharePoint()
    monkeypatch.setattr(mod, "extract_pdf_text", lambda data: data.decode())
    audit = FakeAudit()
    state = SQLiteFinancialStatementState(tmp_path / "audit.sqlite3")
    now = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
    original = audit.append

    def fail_intent(event_type, payload):
        if event_type == "financial.statement.move_intent":
            raise RuntimeError("canonical audit unavailable")
        return original(event_type, payload)

    audit.append = fail_intent
    worker = FinancialStatementMaintenance(
        client=client, state=state, tenant_id="tenant", drive_id="drive",
        audit=audit, now=lambda: now,
    )
    result = worker.run_once(now=now)
    assert result["success"] is False
    assert client.moves == []
    assert state.verify_event_chain()
