from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_deploys_issue_resolution_engine_with_watchdog():
    text = (ROOT / "tools" / "install_self_heal_watchdog.py").read_text(encoding="utf-8")
    assert 'engine_source = repo / "tools" / "issue_resolution_engine.py"' in text
    assert 'copy(engine_source, install_root / "issue_resolution_engine.py", 0o600)' in text
    assert 'issue-resolution engine source is missing' in text


def test_production_convergence_tracks_issue_resolution_engine():
    text = (ROOT / "tools" / "jason_self_heal_watchdog.py").read_text(encoding="utf-8")
    assert '("issue_resolution_engine", "tools/issue_resolution_engine.py"' in text
