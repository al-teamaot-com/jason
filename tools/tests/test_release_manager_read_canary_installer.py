"""Prevent next native Release Manager installation from dropping its read gate."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_native_installer_copies_pinned_read_canary_helper_with_controller():
    s = (ROOT / "tools/install_release_manager.py").read_text()
    controller = 'copy_mode(ROOT / "tools" / "release_manager_host_runner.py"'
    helper = 'copy_mode(ROOT / "tools" / "production_read_canary_gate.py"'
    assert controller in s
    assert helper in s
    assert s.index(controller) < s.index(helper) < s.index("daemon-reload", s.index(helper))
    assert 'LIB / "production_read_canary_gate.py", 0o644' in s


def test_candidate_controller_requires_pinned_canary_module():
    controller = (ROOT / "tools/release_manager_host_runner.py").read_text()
    module = ROOT / "tools/production_read_canary_gate.py"
    assert module.is_file()
    assert "import production_read_canary_gate as owner_read_canary" in controller
    assert "require_authenticated_read_canary(" in controller
    assert "owner_read_canary.begin_authenticated_read_canary(" in controller
