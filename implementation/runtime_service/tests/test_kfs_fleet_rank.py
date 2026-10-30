from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jason_runtime.kfs_meter_history import KfsMeterHistoryStore


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.cur = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cur


def store_with_rows(monkeypatch, rows):
    store = KfsMeterHistoryStore("unused", 5432, "unused", "reader", Path("/unused"))
    cur = FakeCursor(rows)
    monkeypatch.setattr(KfsMeterHistoryStore, "_connect", lambda self: FakeConnection(cur))
    return store, cur


def test_fleet_ranking_distinguishes_missing_boundary_and_sorts(monkeypatch):
    from datetime import timedelta
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = datetime(2026, 10, 30, tzinfo=timezone.utc)
    rows = []
    for device, total, bw, color in (("a", 40, 20, 20), ("b", 100, 80, 20)):
        for counter, delta in (("total", total), ("blackWhite", bw), ("color", color)):
            rows.append((device, counter, 100, start, 100 + delta, end,
                         "Customer", device.upper(), device))
    rows.append(("c", "total", None, None, 150, end, "Customer", "C", "c"))
    rows.append(("c", "blackWhite", None, None, 100, end, "Customer", "C", "c"))
    rows.append(("c", "color", None, None, 50, end, "Customer", "C", "c"))
    store, cursor = store_with_rows(monkeypatch, rows)
    result = store.fleet_rank(arguments={"limit": 2}, start=start, end=end)
    assert [item["device_id"] for item in result["top_devices"]] == ["b", "a"]
    assert result["top_devices"][0]["total_pages"] == 100
    assert result["top_devices"][0]["black_white_pages"] == 80
    assert result["top_devices"][0]["color_pages"] == 20
    assert result["exception_count"] == 1
    assert result["complete"] is False
    assert result["fleet_devices_in_history"] == 3
    assert len(cursor.params) == 14


def test_fleet_ranking_rejects_unbounded_limit(monkeypatch):
    store, _ = store_with_rows(monkeypatch, [])
    with pytest.raises(ValueError, match="limit"):
        store.fleet_rank(arguments={"limit": 9999}, start=datetime.now(timezone.utc),
                         end=datetime.now(timezone.utc))
