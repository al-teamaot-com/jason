from pathlib import Path
import sqlite3

import reflection_exporter as exporter


def test_reflection_metrics_are_aggregate_and_secret_safe(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "reflection.sqlite3"
    c = sqlite3.connect(db)
    c.executescript("""
    create table reflection_records(record_id text);
    create table reflection_user_corrections(correction_id text);
    create table improvement_candidates(candidate_key text, signal_kind text);
    create table improvement_candidate_events(sequence_id integer, candidate_key text, state text);
    create table improvement_regression_evidence(regression_id text, passed integer);
    insert into reflection_records values('r1');
    insert into reflection_user_corrections values('c1');
    insert into improvement_candidates values('k1','user_correction');
    insert into improvement_candidate_events values(1,'k1','observed');
    insert into improvement_candidate_events values(2,'k1','tested');
    insert into improvement_regression_evidence values('g1',1);
    """)
    c.commit(); c.close()
    monkeypatch.setattr(exporter, "DB", db)
    text = exporter.metrics()
    assert "jason_reflection_available 1" in text
    assert "jason_reflection_records 1" in text
    assert 'jason_reflection_candidates{state="tested"} 1' in text
    assert 'jason_reflection_regressions{result="passed"} 1' in text
    assert 'jason_reflection_signals{kind="user_correction"} 1' in text
    assert "k1" not in text and "r1" not in text
