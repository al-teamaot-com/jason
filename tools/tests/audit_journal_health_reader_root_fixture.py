"""Real UID0 file custody and rollback after each native-reader publication.

Runs only in the networkless, read-only CI fixture container with /tmp writable.
No host socket, production state, Owner login, provider or live service exists.
"""
import sys
from pathlib import Path
sys.path[:0] = ['/usr/local/lib/jason/audit-journal/trusted',
                '/usr/local/lib/jason/audit-journal/trusted/implementation']
import os
import json
import tempfile
from types import SimpleNamespace
from contextlib import contextmanager
from tools import audit_journal_health_reader_install as mod
from tools.audit_journal_install_transaction import InstallTransaction

assert os.geteuid() == 0 and sys.flags.isolated == 1
assert not Path('/var/run/docker.sock').exists()
assert not Path('/var/lib/jason/authority').exists()


@contextmanager
def lock():
    yield


for fail_after in range(1, 5):
    with tempfile.TemporaryDirectory(prefix='native-health-repair-', dir='/tmp') as root:
        base = Path(root)
        native = base / 'native'
        native.mkdir(mode=0o755)
        record = base / 'record'
        before = {name: ('old fixture ' + name).encode() for name in mod.BEFORE}
        for name, content in before.items():
            path = native / name
            path.write_bytes(content)
            path.chmod(0o444)
        mod.NATIVE, mod.RECORD = native, record
        mod.BEFORE = {name: mod.digest(content) for name, content in before.items()}
        scope = {'preserved_audit': {'fixture': 'unchanged'}, 'protected_peers': {}, 'unit_configuration_sha256': {}}
        mod.unit_configuration = lambda *a: {}
        mod.preflight = lambda *a: scope
        mod.preserved_audit = lambda *a: scope['preserved_audit']
        mod.props = lambda *a: {'MainPID': '0', 'ActiveState': 'inactive', 'Result': 'success'}
        publishes = []

        def fault(point):
            if point in ('file_published', 'replacement_published'):
                publishes.append(point)
                if len(publishes) == fail_after:
                    raise RuntimeError('fixture power loss after publication')

        class FaultTransaction(InstallTransaction):
            def __init__(self, *args):
                super().__init__(*args, fault=fault)

        mod.InstallTransaction = FaultTransaction
        payload = {name: ('new fixture ' + name).encode() for name in mod.FILES}
        commands = []
        I = SimpleNamespace(command=lambda *a, **k: commands.append(a))
        s = SimpleNamespace(OWNER='fixture-owner')
        try:
            mod.execute(I, s, {'locks': lock, 'owner': lambda _: s.OWNER}, 'f' * 40, payload)
        except RuntimeError as exc:
            assert 'fixture power loss' in str(exc)
        else:
            raise AssertionError('Injected publication failure did not stop acceptance')
        assert record.joinpath('approval.json').is_file(), 'Original Owner evidence was deleted'
        assert json.loads((record / 'transaction.json').read_bytes())['outcome'] == 'rolled_back'
        assert all((native / name).read_bytes() == content for name, content in before.items())
        assert all((native / name).stat().st_uid == 0 and
                   (native / name).stat().st_mode & 0o777 == 0o444 for name in before)
        assert set(x.name for x in native.iterdir()) == set(before), 'Unexpected rollback residue'
        assert len(publishes) == fail_after
print('NATIVE_HEALTH_READER_ALL_FOUR_PUBLICATION_FAILURE_ROLLBACKS=PASS')
