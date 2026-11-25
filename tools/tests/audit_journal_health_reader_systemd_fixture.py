"""Hosted-runner systemd namespace acceptance with synthetic audit data only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

repo = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(repo), str(repo / 'implementation'), str(repo / 'tools')]


def prepare(base):
    from tools.tests.test_audit_journal_native import native, event
    fixture = native.__wrapped__(base)
    profile, controller, store = next(fixture)
    controller.transition(initial=True)
    controller.seal_one()
    store.append_event(event('root-managed-synthetic-namespace'))
    store.close()
    (base / 'scratch').mkdir(mode=0o700)
    value = {name: str(getattr(profile, name)) for name in ('active', 'control', 'archives', 'pending')}
    value.update(custody_uid=os.geteuid(), writer_uid=os.geteuid(), fixture=True)
    (base / 'profile.json').write_text(json.dumps(value))
    fixture.close()


def verify(base):
    from orchestrator.segmented_journal import JournalProfile
    import audit_journal_health_private_reader as reader
    assert os.geteuid() != 0, 'The synthetic reader must run without root identity'
    profile = JournalProfile(**{k: Path(v) if k in ('active', 'control', 'archives', 'pending') else v
                                for k, v in json.loads((base / 'profile.json').read_text()).items()})
    assert os.statvfs(base).f_flag & os.ST_RDONLY, 'A real root-managed readonly mount is required'
    before = hashlib.sha256(profile.active.read_bytes()).hexdigest()
    try:
        with profile.active.open('ab'):
            pass
    except OSError:
        pass
    else:
        raise AssertionError('Root sandbox allowed canonical fixture modification')
    scratch = base / 'scratch'
    with reader.readonly_active_copy(profile, temp_root=scratch) as (private, catalog, digest):
        with sqlite3.connect(private.as_uri() + '?mode=ro', uri=True) as connection:
            assert connection.execute('SELECT count(*) FROM orchestration_events').fetchone()[0] == 1
    proof = reader.full_integrity(profile.active, profile=profile, temp_root=scratch)
    assert proof['active_snapshot'] == proof['active_restore']
    assert reader.validate_full_evidence({'orchestration_journal': proof}, profile=profile, temp_root=scratch)
    assert not list(scratch.iterdir()), 'Private scratch was not cleaned'
    assert hashlib.sha256(profile.active.read_bytes()).hexdigest() == before
    assert not Path(str(profile.active) + '-wal').exists()
    assert not Path(str(profile.active) + '-shm').exists()
    print('ROOT_SYSTEMD_PRIVATE_READER_READONLY_SOURCE_AND_PROOF=PASS')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('operation', choices=('prepare', 'verify'))
    p.add_argument('base', type=Path)
    args = p.parse_args()
    assert not str(args.base.resolve()).startswith(('/var/lib/jason', '/srv/jason', '/etc/jason'))
    (prepare if args.operation == 'prepare' else verify)(args.base)
