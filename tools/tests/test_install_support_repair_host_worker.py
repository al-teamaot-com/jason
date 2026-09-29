from pathlib import Path


def test_support_repair_units_exist():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service').is_file()
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer').is_file()
    assert (root / 'tools/support_repair_host_worker.py').is_file()
