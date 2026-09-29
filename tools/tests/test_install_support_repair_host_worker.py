from pathlib import Path


def test_support_repair_units_exist():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service').is_file()
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer').is_file()
    assert (root / 'tools/support_repair_host_worker.py').is_file()


def test_support_repair_timer_runs_daily_at_0230_and_remains_persistent():
    root = Path(__file__).resolve().parents[2]
    timer = (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer').read_text()
    assert 'OnCalendar=*-*-* 02:30:00' in timer
    assert 'AccuracySec=1min' in timer
    assert 'Persistent=true' in timer
    assert 'OnUnitInactiveSec=' not in timer
    assert 'OnBootSec=' not in timer
    assert 'OnUnitActiveSec=' not in timer
