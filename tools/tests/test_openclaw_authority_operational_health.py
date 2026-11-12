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


def _synthetic_full_health(monkeypatch, tmp_path, *, orchestration_present=True,
                           orchestration_integrity='ok', backup_integrity='ok'):
    import threading

    module = _load_module()
    paths = {}
    for name in ('authority', 'replay', 'security_audit', 'orchestration_audit'):
        target = tmp_path / (name + '.sqlite3')
        if name != 'orchestration_audit' or orchestration_present:
            target.write_bytes(b'synthetic-only')
            target.chmod(0o600)
        paths[name] = target
    registry = tmp_path / 'registry.json'
    registry.write_text('{"keys":[{"status":"active"}]}')
    registry.chmod(0o600)
    args = module.parser().parse_args([
        '--authority-database', str(paths['authority']),
        '--replay-database', str(paths['replay']),
        '--security-audit', str(paths['security_audit']),
        '--orchestration-audit', str(paths['orchestration_audit']),
        '--key-registry', str(registry),
        '--backup-temp-root', str(tmp_path),
    ])
    orchestrator_started = threading.Event()
    backup_completed = threading.Event()
    observed = []

    def fake_integrity(path):
        observed.append(('integrity', path.name))
        if path == paths['orchestration_audit']:
            orchestrator_started.set()
            assert backup_completed.wait(3), (
                'orchestration integrity must overlap the AUTHORITY backup '
                'without skipping either full check'
            )
            return orchestration_integrity
        return 'ok'

    def fake_backup(source, root):
        assert root == tmp_path
        assert orchestrator_started.wait(3), 'orchestration scan not started'
        observed.append(('backup', source.name))
        backup_completed.set()
        return {
            'backup_integrity': backup_integrity,
            'restore_integrity': 'ok',
            'backup_mode': '0o600',
            'restore_mode': '0o600',
            'counts_match': True,
        }

    monkeypatch.setattr(module, 'sqlite_integrity', fake_integrity)
    monkeypatch.setattr(module, 'backup_restore_proof', fake_backup)
    monkeypatch.setattr(module, 'authority_counts', lambda _: {'identities': 1})
    monkeypatch.setattr(module, 'active_delegation_state',
                        lambda _: {'active': 0})
    monkeypatch.setattr(module, 'registry_health',
                        lambda _: {'present': True, 'mode': '0o600',
                                   'active_records': 1})
    return module, args, observed, paths


def test_orchestration_full_check_overlaps_real_authority_proof_not_skipped(
        monkeypatch, tmp_path, capsys):
    import json
    module, args, observed, paths = _synthetic_full_health(monkeypatch, tmp_path)
    assert module.run(args) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['status'] == 'pass'
    assert report['failures'] == []
    assert report['provider_contacted'] is False
    assert report['provider_credentials_used'] is False
    assert set(report['completed_stage_seconds']) == {
        'authority', 'replay', 'security_audit',
        'authority_backup_restore', 'orchestration_audit',
    }
    assert all(row['integrity'] == 'ok' for row in report['files'].values())
    assert set(name for op, name in observed if op == 'integrity') == {
        path.name for path in paths.values()
    }
    assert observed.count(('backup', paths['authority'].name)) == 1
    assert captured.err.count('JASON_FULL_INTEGRITY_STAGE_V1|') == 5
    assert 'quick_check' not in captured.err


def test_corrupt_orchestration_integrity_still_fails_closed(
        monkeypatch, tmp_path, capsys):
    import json
    module, args, _observed, _paths = _synthetic_full_health(
        monkeypatch, tmp_path, orchestration_integrity='corrupt'
    )
    assert module.run(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'fail'
    assert 'orchestration_audit_integrity' in report['failures']
    assert report['files']['orchestration_audit']['integrity'] == 'corrupt'


def test_authority_restore_bad_result_still_fails_closed(
        monkeypatch, tmp_path, capsys):
    import json
    module, args, _observed, _paths = _synthetic_full_health(
        monkeypatch, tmp_path, backup_integrity='not ok'
    )
    assert module.run(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'fail'
    assert 'authority_backup_restore' in report['failures']


def test_missing_orchestration_db_never_generates_false_pass(
        monkeypatch, tmp_path, capsys):
    import json
    module, args, _observed, _paths = _synthetic_full_health(
        monkeypatch, tmp_path, orchestration_present=False
    )
    # No background orchestration scan can start for a missing database,
    # and the synthetic backup needs to tolerate that fail-closed path.
    monkeypatch.setattr(module, 'backup_restore_proof', lambda *_: {
        'backup_integrity': 'ok', 'restore_integrity': 'ok',
        'backup_mode': '0o600', 'restore_mode': '0o600',
        'counts_match': True,
    })
    assert module.run(args) == 2
    report = json.loads(capsys.readouterr().out)
    assert 'orchestration_audit_missing' in report['failures']
    assert report['files']['orchestration_audit']['integrity'] is None


def test_real_tiny_sqlite_full_proof_and_backup_restore_still_pass(
        tmp_path, capsys):
    """End-to-end preproduction smoke with four actual SQLite DBs."""
    import json
    module = _load_module()
    files = {}
    for name in ('authority', 'replay', 'security_audit', 'orchestration_audit'):
        p = tmp_path / (name + '.sqlite3')
        with sqlite3.connect(p) as con:
            if name == 'authority':
                for table in ('identities', 'authority_grants', 'approvals',
                              'execution_contexts', 'delegations'):
                    con.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, payload TEXT)')
                con.execute("INSERT INTO identities(id) VALUES (1)")
            else:
                con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, payload TEXT)')
                con.execute("INSERT INTO events(payload) VALUES ('synthetic')")
            con.commit()
        p.chmod(0o600)
        files[name] = p
    registry = tmp_path / 'keys.json'
    registry.write_text(json.dumps({'keys': [{'status': 'active'}]}))
    registry.chmod(0o600)
    scratch = tmp_path / 'backup-tmp'
    scratch.mkdir()
    args = module.parser().parse_args([
        '--authority-database', str(files['authority']),
        '--replay-database', str(files['replay']),
        '--security-audit', str(files['security_audit']),
        '--orchestration-audit', str(files['orchestration_audit']),
        '--key-registry', str(registry),
        '--backup-temp-root', str(scratch),
    ])
    assert module.run(args) == 0
    result = capsys.readouterr()
    data = json.loads(result.out)
    assert data['status'] == 'pass' and data['failures'] == []
    assert data['backup_restore_proof']['backup_integrity'] == 'ok'
    assert data['backup_restore_proof']['restore_integrity'] == 'ok'
    assert data['backup_restore_proof']['counts_match'] is True
    assert data['authority_counts']['identities'] == 1
    assert all(info['integrity'] == 'ok' for info in data['files'].values())
    assert set(data['files']) == set(files)
    assert not list(scratch.iterdir()), 'Backup scratch must be cleaned'
    assert result.err.count('JASON_FULL_INTEGRITY_STAGE_V1|') == 5
