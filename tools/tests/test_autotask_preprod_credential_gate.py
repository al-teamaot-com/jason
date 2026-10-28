import os
from pathlib import Path
from tools.autotask_preprod_credential_gate import check


def test_missing_is_not_ready(tmp_path):
    assert not check(tmp_path / 'absent')['ready']


def test_symlink_is_rejected(tmp_path):
    target = tmp_path / 'real'
    target.mkdir(mode=0o700)
    link = tmp_path / 'link'
    link.symlink_to(target)
    assert not check(link)['ready']


def test_private_isolated_metadata_only(tmp_path):
    root = tmp_path / 'credential'
    root.mkdir(mode=0o700)
    for name in ('role_id', 'secret_id'):
        p = root / name
        p.write_text('placeholder-not-real')
        p.chmod(0o600)
    assert check(root)['ready']
    (root / 'secret_id').chmod(0o644)
    assert not check(root)['ready']


def test_no_unscoped_directory(tmp_path):
    root = tmp_path / 'credential'
    root.mkdir(mode=0o755)
    assert not check(root)['ready']
