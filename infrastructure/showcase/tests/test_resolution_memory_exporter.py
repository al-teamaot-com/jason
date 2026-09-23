from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resolution_memory_exporter as exporter


def test_metrics_expose_only_aggregate_resolution_memory_state(tmp_path, monkeypatch):
    db = tmp_path / "resolution.sqlite3"
    c = sqlite3.connect(db)
    c.execute("create table resolution_cases(case_id text, organization_id text, client_id text, status text)")
    c.executemany("insert into resolution_cases values(?,?,?,?)", [("C1","aot","client-a","verified"),("C2","aot","client-b","observed")])
    c.commit(); c.close()
    monkeypatch.setattr(exporter, "DB", db)
    text = exporter.metrics()
    assert 'jason_resolution_memory_cases{status="all"} 2' in text
    assert 'jason_resolution_memory_cases{status="verified"} 1' in text
    assert 'jason_resolution_memory_client_scopes 2' in text
    assert "client-a" not in text and "client-b" not in text and "C1" not in text
