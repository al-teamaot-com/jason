from pathlib import Path


def test_support_repair_units_exist():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service').is_file()
    assert (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer').is_file()
    assert (root / 'tools/support_repair_host_worker.py').is_file()
    assert (root / 'tools/owner_approved_development_worker.py').is_file()
    assert (root / 'tools/todo_engineering_intake.py').is_file()
    assert (root / 'tools/todo_release_bridge.py').is_file()


def test_engineering_service_runs_support_before_owner_approved_development():
    root = Path(__file__).resolve().parents[2]
    service = (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service').read_text()
    support_index = service.index('support_repair_host_worker.py')
    development_index = service.index('owner_approved_development_worker.py')
    assert support_index < development_index
    assert '/home/al/jason-worktrees/owner-approved-development' in service


def test_support_repair_timer_runs_daily_at_0230_and_remains_persistent():
    root = Path(__file__).resolve().parents[2]
    timer = (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer').read_text()
    assert 'OnCalendar=*-*-* 02:30:00' in timer
    assert 'AccuracySec=1min' in timer
    assert 'Persistent=true' in timer
    assert 'OnUnitInactiveSec=' not in timer
    assert 'OnBootSec=' not in timer
    assert 'OnUnitActiveSec=' not in timer


def test_engineering_service_orders_support_todo_development_and_release_bridge():
    root = Path(__file__).resolve().parents[2]
    service = (root / 'infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service').read_text()
    support_index = service.index('support_repair_host_worker.py')
    todo_index = service.index('todo_engineering_intake.py')
    development_index = service.index('owner_approved_development_worker.py')
    bridge_index = service.index('todo_release_bridge.py')
    assert support_index < todo_index < development_index < bridge_index
