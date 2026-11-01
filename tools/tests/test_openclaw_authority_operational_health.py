from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'openclaw_authority_operational_health.py'


def _load_module():
    spec = importlib.util.spec_from_file_location('openclaw_authority_operational_health', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backup_restore_proof_uses_requested_temp_root_and_cleans_up(tmp_path):
    module = _load_module()
    source = tmp_path / 'authority.sqlite3'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE identities (id INTEGER PRIMARY KEY)')
        connection.execute('INSERT INTO identities DEFAULT VALUES')
        connection.commit()
    source.chmod(0o600)

    scratch = tmp_path / 'archive-scratch'
    scratch.mkdir()
    before = set(scratch.iterdir())
    result = module.backup_restore_proof(source, scratch)
    after = set(scratch.iterdir())

    assert result['backup_integrity'] == 'ok'
    assert result['restore_integrity'] == 'ok'
    assert result['counts_match'] is True
    assert result['backup_mode'] == '0o600'
    assert result['restore_mode'] == '0o600'
    assert before == after == set()


def test_parser_accepts_explicit_backup_temp_root(tmp_path):
    module = _load_module()
    args = module.parser().parse_args(['--backup-temp-root', str(tmp_path)])
    assert args.backup_temp_root == tmp_path
