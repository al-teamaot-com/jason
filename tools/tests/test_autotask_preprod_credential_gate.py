import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.autotask_preprod_credential_gate import check


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / 'credential'
    root.mkdir(mode=0o700)
    for name in ('role_id', 'secret_id'):
        path = root / name
        path.write_text('synthetic-placeholder-not-a-real-secret')
        path.chmod(0o600)
    return root


def test_missing_is_not_ready(tmp_path):
    assert not check(tmp_path / 'absent')['ready']


def test_symlink_is_rejected(tmp_path):
    target = _private_root(tmp_path)
    link = tmp_path / 'link'
    link.symlink_to(target)
    assert not check(link)['ready']


def test_ancestor_symlink_is_rejected(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    _private_root(target)
    alias = tmp_path / 'alias'
    alias.symlink_to(target, target_is_directory=True)
    result = check(alias / 'credential')
    assert result == {'ready': False, 'reason': 'SYMLINK_IN_CREDENTIAL_PATH'}


def test_noncanonical_parent_traversal_is_rejected(tmp_path):
    path = tmp_path / 'credentials' / '..' / 'credential'
    assert check(path)['reason'] == 'NON_CANONICAL_CREDENTIAL_DIRECTORY'


def test_private_isolated_metadata_only(tmp_path):
    root = _private_root(tmp_path)
    assert check(root) == {
        'ready': True,
        'reason': 'ISOLATION_METADATA_CHECK_PASSED_NOT_AUTHORIZATION_PROOF',
    }
    (root / 'secret_id').chmod(0o644)
    assert not check(root)['ready']


def test_no_unscoped_directory(tmp_path):
    root = _private_root(tmp_path)
    root.chmod(0o755)
    assert check(root)['reason'] == 'DIRECTORY_PERMISSIONS_TOO_BROAD'


def test_hardlink_secret_is_rejected(tmp_path):
    root = _private_root(tmp_path)
    os.link(root / 'role_id', tmp_path / 'other-name')
    assert check(root)['reason'] == 'CREDENTIAL_METADATA_INVALID'


def test_special_file_is_rejected(tmp_path):
    root = _private_root(tmp_path)
    (root / 'secret_id').unlink()
    os.mkfifo(root / 'secret_id', mode=0o600)
    assert not check(root)['ready']


def test_secret_file_owner_mismatch_is_rejected(tmp_path):
    root = _private_root(tmp_path)
    original = Path.stat

    def spoof_uid(self, *a, **kw):
        result = original(self, *a, **kw)
        if self == root / 'secret_id':
            # Only metadata is changed; the test never reads the file.
            return SimpleNamespace(
                st_uid=os.geteuid() + 1,
                st_mode=result.st_mode,
                st_nlink=result.st_nlink,
                st_size=result.st_size,
            )
        return result

    with patch.object(Path, 'stat', autospec=True, side_effect=spoof_uid):
        assert check(root)['reason'] == 'CREDENTIAL_FILE_OWNER_MISMATCH'


def test_directory_owner_mismatch_is_rejected(tmp_path):
    root = _private_root(tmp_path)
    with patch('tools.autotask_preprod_credential_gate.os.geteuid',
               return_value=os.geteuid() + 1):
        assert check(root)['reason'] == 'CREDENTIAL_DIRECTORY_OWNER_MISMATCH'


def test_check_never_reads_credential_content(tmp_path):
    root = _private_root(tmp_path)
    with (patch.object(Path, 'read_text', side_effect=AssertionError('read_text prohibited')),
          patch.object(Path, 'read_bytes', side_effect=AssertionError('read_bytes prohibited')),
          patch('builtins.open', side_effect=AssertionError('open prohibited'))):
        assert check(root)['ready']


def test_missing_is_not_logged_as_secret(tmp_path, capsys):
    root = tmp_path / 'missing'
    check(root)
    assert capsys.readouterr().out == ''
