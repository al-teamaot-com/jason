import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'release_manager_controller_recovery.py'
spec = importlib.util.spec_from_file_location('release_manager_controller_recovery', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_noncanonical_locations_fail_closed(tmp_path):
    with pytest.raises(ValueError, match='canonical'):
        m.recover(tmp_path, tmp_path / 'controller.py', 'a' * 40)


def test_incorrect_git_revision_fail_closed(tmp_path):
    with patch.object(m, 'DEFAULT_REPO', tmp_path), patch.object(m, 'DEFAULT_TARGET', tmp_path / 'controller.py'):
        with patch.object(m, 'git', return_value=b'b' * 40):
            with pytest.raises(ValueError, match='protected main'):
                m.recover(tmp_path, tmp_path / 'controller.py', 'a' * 40)


def test_matching_revision_dry_run_is_nonmutating(tmp_path):
    target = tmp_path / 'controller.py'
    target.write_bytes(b'old')
    source = b'def _read_protected_snapshot():\n    pass\n'
    with patch.object(m, 'DEFAULT_REPO', tmp_path), patch.object(m, 'DEFAULT_TARGET', target):
        with patch.object(m, 'git', side_effect=[b'a' * 40, source]):
            result = m.recover(tmp_path, target, 'a' * 40)
    assert result['changed']
    assert target.read_bytes() == b'old'
