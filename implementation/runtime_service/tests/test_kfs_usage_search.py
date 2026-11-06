from datetime import datetime, timezone
from pathlib import Path

from jason_runtime.kfs_meter_history import KfsMeterHistoryStore


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params):
        self.sql, self.params = sql, params
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self.cursor_value


def make_store(monkeypatch, raw_rows):
    cur = Cursor(raw_rows)
    store = KfsMeterHistoryStore("unused", 5432, "unused", "reader", Path("/unused"))
    monkeypatch.setattr(KfsMeterHistoryStore, "_connect", lambda self: Connection(cur))
    return store, cur


def test_usage_search_returns_unsorted_generic_records_and_exceptions(monkeypatch):
    start = datetime(2026, 10, 27, tzinfo=timezone.utc)
    end = datetime(2026, 11, 5, tzinfo=timezone.utc)
    snapshot = end
    rows = []
    # Intentionally smaller usage first. The source must not rank.
    for device, serial, equipment, model, total, bw, color, printer, copier, scans in (
        ("a", "SERIALA1", "ID-A", "Model A", 40, 30, 10, 35, 5, 9),
        ("b", "SERIALB2", "ID-B", "Model B", 100, 80, 20, 90, 10, 12),
    ):
        for counter, delta in (
            ("total", total), ("blackWhite", bw), ("color", color),
            ("printerTotal", printer), ("copierTotal", copier), ("scanTotal", scans),
        ):
            rows.append((
                device, counter, 100, start, 100 + delta, end,
                "Client " + device.upper(), equipment, serial, model,
                "run-1", snapshot, 2, 0, 2, 2,
            ))
    store, cur = make_store(monkeypatch, rows)
    data = store.usage_search(arguments={}, start=start, end=end)

    assert [item["device_id"] for item in data["records"]] == ["a", "b"]
    assert data["records"][0]["total_impressions"] == 40
    assert data["records"][1]["total_impressions"] == 100
    assert data["records"][1]["printer_impressions"] == 90
    assert data["records"][1]["copier_impressions"] == 10
    assert data["records"][1]["scans"] == 12
    assert all(item["usage_status"] == "verified" for item in data["records"])
    assert all(item["inventory_coverage_verified"] is True for item in data["records"])
    assert "ORDER BY b.device_id" in cur.sql
    assert "DESC" not in cur.sql.split("ORDER BY b.device_id", 1)[-1]


def test_usage_search_preserves_missing_meter_as_exception(monkeypatch):
    start = datetime(2026, 10, 27, tzinfo=timezone.utc)
    end = datetime(2026, 11, 5, tzinfo=timezone.utc)
    rows = []
    for counter in ("total", "blackWhite", "color", "printerTotal", "copierTotal", "scanTotal"):
        rows.append((
            "x", counter, None, None, None, None,
            "", "ID-X", "SERIALX1", "Model X",
            "run-1", end, 1, 0, 1, 1,
        ))
    store, _ = make_store(monkeypatch, rows)
    data = store.usage_search(arguments={}, start=start, end=end)
    row = data["records"][0]
    assert row["usage_status"] == "exception"
    assert row["total_impressions"] is None
    assert row["customer_mapping_status"] == "not_found"
    assert any("meter" in warning for warning in data["warnings"])
