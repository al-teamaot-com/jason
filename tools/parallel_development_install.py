#!/usr/bin/env python3
"""Exact scoped engineering-worker activation using existing native Owner gates.

No runtime deployment, scheduler change, freeze exception or provider write.
The root entry is usable only after protected merge/CI and an externally
SHA-pinned isolated root launch. Ordinary import and review are nonmutating.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
import errno
from datetime import datetime, timezone
import fnmatch
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
BASE = Path('/home/al/.local/lib/jason')
SPOOL = Path('/var/lib/jason/openclaw/support-repair')
MANAGER = SPOOL.parent / 'release-manager'
RECORDS = Path('/var/lib/jason-owner-release/parallel-development-install')
SOURCE = BASE / 'engineering-worker-source'
SOURCE_TARGET = '/srv/jason/archive/engineering-artifacts/pmv4-e-engineering-source-1a7e7c1b03fce7dffa3ac6aab26480d614327e69'
ACCEPTED_SOURCE = '1a7e7c1b03fce7dffa3ac6aab26480d614327e69'
ROLLBACK = 'd1b8c196dadd4b672ec8ba47075f27bb61c98d63'
ACTION = 'INSTALL-EXACT-PARALLEL-DEVELOPMENT-COMPONENT'
REMOTE = 'https://github.com/al-teamaot-com/jason.git'
FILES = {
    'dependency_conflict_service.py': ('tools/dependency_conflict_service.py', 0o600),
    'isolated_service_common.py': ('tools/isolated_service_common.py', 0o600),
    'development-concurrency-scopes.json': ('config/development-concurrency-scopes.json', 0o600),
    'owner_approved_development_worker.py': ('tools/owner_approved_development_worker.py', 0o700),
}
WORKER = 'owner_approved_development_worker.py'
DEPS = ('support_repair_host_worker.py', 'engineering_evidence_tools.py',
        'todo_release_bridge.py', 'change_integration_gate.py', 'documentation_impact_gate.py',
        'operational_acceptance_reader.py', 'release_manager_gate.py',
        'engineering_pipeline.py', 'pmv3_engineering_controller.py', 'pmv3_worker_release_gate.py')
NATIVE = Path('/usr/local/lib/jason/pmv4-e-bootstrap/native/tools')
PINNED = {
    'tools/pmv4_e_dispatch_install.py': '6d276b67538e1bf988a751dc9ef10ac6996cc6955ff6bc3e562a506da13282f7',
    str(NATIVE / 'pmv4_e_ci_refresh.py'): 'f4d24dad7f69d0add18d7d852df1add7bc36981242c4725ee33b07f7583108d7',
    str(NATIVE / 'manual_release_scope.py'): '7ec8c203293927ea6c56b7f4c52d50509c725382b746e49ad63323ca79dd80ca',
    '/opt/jason/current/tools/production_drift_guard.py': '03cfc08c7b8d4d9f63d22700c7a5dc6f58ff9c19b8d7060ab1cdb41192b9c56a',
    '/opt/jason/independent-component-release/trusted/tools/pmv4_host_release_guard.py':
        '223cc0dca981461cb93782afad5804efa0740a06b3dd51becf20bbc856371bfc',
}
CONTROLS = {
    MANAGER / 'production-deployment-freeze': (1000, 0o600, 'bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f'),
    MANAGER / 'auto-promotion-incident-hold': (1000, 0o664, '11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0'),
    SPOOL / 'pmv3-engineering-owner-pause.json': (1000, 0o600, '4a5de8286bf9d77842ca94dafe6f1d38c1a835e8f12bc0dfda46b7a3cf867747'),
}
AUDIT = Path('/var/lib/jason-audit-journal/control/forward-release-status.json')
FORWARD_SCOPE_SHA256 = '697210854d0a0140d3a672750ad84d043e5ac99db117abd6043469312d017fb7'
FORWARD_ACTION = 'RECOVER-SEGMENTED-AUDIT-WITHOUT-LEGACY-REBUILD'
FORWARD_ARCHIVED_EVENTS = 34616410
DESIRED = Path('/etc/jason/release-readback-recovery/production-desired-state.json')
# The shadow gateway is preproduction-only (production-core=excluded), and
# is absent from the accepted LKG required_containers policy. Its stopped
# state must not block an unrelated governed production host-worker release.
# Root drift, protected container images, native core guard and locks remain
# mandatory for the actual production peers.
PEERS = ('jason-runtime', 'jason-mcp-pilot', 'jason-pmv4-ticket-core',
         'jason-teams-gateway', 'openbao')
USER = ('/usr/sbin/runuser', '-u', 'al', '--', '/usr/bin/env', '-i',
        'HOME=/home/al', 'PATH=/usr/local/bin:/usr/bin:/bin',
        'LANG=C.UTF-8', 'XDG_RUNTIME_DIR=/run/user/1000',
        'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
        'GIT_CONFIG_NOSYSTEM=1', 'GIT_CONFIG_GLOBAL=/dev/null',
        'GIT_OPTIONAL_LOCKS=0', 'GIT_NO_REPLACE_OBJECTS=1',
        'GIT_GRAFT_FILE=/dev/null', 'GIT_TERMINAL_PROMPT=0',
        'GIT_CONFIG_COUNT=2', 'GIT_CONFIG_KEY_0=core.fsmonitor',
        'GIT_CONFIG_VALUE_0=false', 'GIT_CONFIG_KEY_1=core.hooksPath',
        'GIT_CONFIG_VALUE_1=/dev/null')


def need(ok, reason):
    if not ok:
        raise PermissionError('PARALLEL_COMPONENT_' + reason)


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def exact_sha(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{40}', value) is not None


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path, uid, mode=None, *, source=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        m = os.fstat(f.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_uid == uid and (m.st_gid == uid or (source and uid == 1000 and m.st_gid == 984)) and m.st_nlink == 1
             and not m.st_mode & 0o002
             and (not m.st_mode & 0o020 or (uid == 0 and m.st_gid == 0)
                  or (path == MANAGER / 'auto-promotion-incident-hold' and uid == m.st_gid == 1000 and mode == 0o664))
             and 0 < m.st_size <= 2000000
             and (mode is None or stat.S_IMODE(m.st_mode) == mode), 'FILE_CUSTODY:' + path.name)
        raw = f.read(2000001)
        need(len(raw) == m.st_size, 'FILE_CHANGED:' + path.name)
        return raw


def native_code(path, key, uid, mode=None):
    raw = read(path, uid, mode, source=uid == 1000)
    need(digest(raw) == PINNED[key], 'PINNED_CODE_CHANGED:' + path.name)
    ns = {'__name__': 'reviewed_parallel_' + path.stem, '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), ns)
    return ns


def command(args, timeout=45, data=None):
    p = subprocess.run(args, cwd='/', env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                      'HOME': '/root', 'LANG': 'C.UTF-8'},
                       input=data, capture_output=True, timeout=timeout, check=False)
    need(p.returncode == 0 and len(p.stdout) <= 6000000,
         'COMMAND_FAILED:' + Path(args[0]).name + ':' + str(p.returncode))
    return p.stdout


def git(repo, *args):
    return command([*USER, '/usr/bin/git', '-C', str(repo), *args])


def git_paths(repo, candidate, head):
    need(exact_sha(candidate) and exact_sha(head), 'PROTECTED_REVISION_INVALID')
    git(repo, 'merge-base', '--is-ancestor', candidate, head)
    git(repo, 'merge-base', '--is-ancestor', ROLLBACK, candidate)
    commits = git(repo, 'rev-list', candidate + '..' + head).decode().splitlines()
    need(len(commits) <= 1000 and all(exact_sha(x) for x in commits), 'NEWER_HISTORY_UNBOUNDED')
    touched = set()
    for commit in commits:
        raw = git(repo, 'diff-tree', '-r', '-m', '--no-commit-id', '--no-renames', '--name-only', '-z', commit)
        for path in raw.decode('utf-8').split('\0'):
            if not path:
                continue
            need(not path.startswith('/') and '..' not in path.split('/') and '\n' not in path,
                 'NEWER_PATH_INVALID')
            touched.add(path)
        need(len(touched) <= 10000, 'NEWER_PATHS_UNBOUNDED')
    return touched


def reviewed_paths():
    return ({src for src, _ in FILES.values()} | {'tools/' + x for x in DEPS}
            | {'tools/parallel_development_install.py', 'tools/pmv4_e_dispatch_install.py',
               'tools/manual_release_scope.py', 'tools/pmv4_e_ci_refresh.py',
               'tools/pmv4_host_release_guard.py', '.github/workflows/validate.yml',
               'tools/tests/test_parallel_development_install.py',
               'tools/tests/test_parallel_development_claim_integration.py',
               'tools/tests/test_parallel_development_admission.py',
               'tools/tests/test_parallel_development_board.py', 'config/release-manager-policy.json',
               'config/production-desired-state.json', 'tools/install_support_repair_host_worker.py'})


def check_newer_paths(touched, protected_globs):
    need(isinstance(protected_globs, list) and protected_globs
         and all(isinstance(x, str) and x for x in protected_globs), 'PROTECTED_POLICY_INVALID')
    conflicts = sorted(p for p in touched if p in reviewed_paths()
                       or any(fnmatch.fnmatchcase(p, glob) for glob in protected_globs))
    need(not conflicts, 'NEWER_SCOPE_OR_CONTROL_CHANGE:' + ','.join(conflicts[:6]))


def source_and_ci(candidate):
    need(exact_sha(candidate) and git(REPO, 'rev-parse', 'HEAD').decode().strip() == candidate
         and not git(REPO, 'status', '--porcelain', '--untracked-files=all').strip()
         and git(REPO, 'remote', 'get-url', 'origin').decode().strip() == REMOTE
         and git(REPO, 'rev-parse', '--is-shallow-repository').decode().strip() == 'false',
         'REVIEWED_SOURCE_NOT_EXACT')
    helper = native_code(NATIVE / 'pmv4_e_ci_refresh.py', str(NATIVE / 'pmv4_e_ci_refresh.py'), 0, 0o444)
    attestor = helper['load_pinned_attestor'](helper['SOURCE'], production=True)
    helper['paginate_required_checks'](attestor)
    result = attestor['verify_ci'](candidate)
    head = result['protected_main']
    need(result['candidate_sha'] == candidate and result['required_ci_passed'] is True
         and result['protected_main_ancestor'] is True
         and command([*USER, '/usr/bin/git', 'ls-remote', REMOTE, 'refs/heads/main']).decode().split()
         == [head, 'refs/heads/main'], 'PROTECTED_CI_OR_MAIN_UNVERIFIED')
    policies = []
    for revision in (ROLLBACK, candidate):
        patterns = json.loads(git(REPO, 'show', revision + ':config/release-manager-policy.json'))['protected_core_globs']
        need(isinstance(patterns, list) and patterns and all(type(x) is str and x for x in patterns),
             'PROTECTED_POLICY_INVALID')
        policies.extend(patterns)
    check_newer_paths(git_paths(REPO, candidate, head), policies)
    code = {}
    for path in sorted(reviewed_paths()):
        raw = git(REPO, 'show', candidate + ':' + path)
        need(raw == read(REPO / path, 1000, source=True), 'SOURCE_BYTES_CHANGED:' + path)
        code[path] = raw
    need(code['tools/parallel_development_install.py'] == Path(__file__).read_bytes()
         and digest(code['tools/pmv4_e_dispatch_install.py']) == PINNED['tools/pmv4_e_dispatch_install.py'],
         'EXECUTED_INSTALLER_OR_PRIMITIVES_CHANGED')
    return code, policies


# Use the current trusted exhaustive reviewer, but only over the exact
# component closure; unrelated registry counts are observations, not consent.
SCAN = """
import json,sys
from pathlib import Path
path, candidate, *repos = sys.argv[1:]
ns={'__name__':'parallel_scope_scan','__file__':path}
exec(compile(Path(path).read_bytes(),path,'exec'),ns)
changed=set(json.load(sys.stdin))
prs,_=ns['open_pr_overlaps']('al-teamaot-com/jason',changed)
if prs: raise SystemExit('overlapping open PRs')
for repo in repos:
    overlaps,_,_,_=ns['dirty_worktrees'](Path(repo),changed,candidate)
    if overlaps: raise SystemExit('overlapping dirty worktrees')
print('COMPONENT_SCOPE_COMPLETE_NO_OVERLAPS')
"""


def recheck_overlaps(candidate):
    path = NATIVE / 'manual_release_scope.py'
    need(digest(read(path, 0, 0o444)) == PINNED[str(path)], 'NATIVE_SCOPE_REVIEWER_CHANGED')
    paths = {src for src, _ in FILES.values()} | {'tools/' + x for x in DEPS}
    raw = command([*USER, '/usr/bin/python3', '-I', '-B', '-c', SCAN, str(path), candidate,
                   str(REPO), '/home/al/projects/jason', str(SOURCE)],
                  timeout=900, data=canon(sorted(paths)))
    need(raw.strip() == b'COMPONENT_SCOPE_COMPLETE_NO_OVERLAPS', 'OVERLAP_SCAN_UNVERIFIED')


def unit(name, user=False):
    prefix = [*USER, '/usr/bin/systemctl', '--user'] if user else ['/usr/bin/systemctl']
    return dict(x.split('=', 1) for x in command([*prefix, 'show', name, '-p', 'ActiveState',
                '-p', 'MainPID', '-p', 'Result', '-p', 'ExecMainStatus']).decode().splitlines() if '=' in x)


def control_bytes():
    values = {}
    for path, (uid, mode, pin) in CONTROLS.items():
        actual = digest(read(path, uid, mode))
        need(actual == pin, 'FREEZE_HOLD_OR_PAUSE_CHANGED:' + path.name)
        values[str(path)] = actual
    return values


def forward_audit_accepted(row):
    """Exact root-owned no-restore release acceptance, never legacy/provisional.

    The owner-signed recovery's scope is pinned: a different/replayed scope,
    queued action or self-reported healthy container cannot admit development.
    Downstream independent native controls/fast/full/drift remain mandatory.
    """
    return (isinstance(row, dict)
            and row.get('schema_version') == '1.0'
            and row.get('action') == FORWARD_ACTION
            and row.get('scope_sha256') == FORWARD_SCOPE_SHA256
            and row.get('phase') == 'accepted'
            and row.get('status') == 'accepted'
            and row.get('no_legacy_rebuild') is True
            and row.get('provider_calls') == 0 and type(row.get('provider_calls')) is int
            and type(row.get('initial_archive_events')) is int
            and row['initial_archive_events'] == FORWARD_ARCHIVED_EVENTS
            and type(row.get('root_free_bytes')) is int
            and row['root_free_bytes'] > 35_000_000_000
            and type(row.get('sealed_segments')) is int
            and row['sealed_segments'] >= 2
            and all(row.get(k) == 'pass' for k in ('full_health','fast_health','drift'))
            and row.get('breaker') == 'closed')


def audit_recovery_service_complete():
    old = unit('jason-audit-journal-release.service')
    new = unit('jason-audit-journal-no-restore-release.service')
    return (all(old.get(k) == v for k, v in (
                ('ActiveState','inactive'),('MainPID','0'),('Result','success'),
                ('ExecMainStatus','0')))
            and all(new.get(k) == v for k, v in (
                ('ActiveState','inactive'),('MainPID','0'),('Result','success'),
                ('ExecMainStatus','0')))
            and unit('jason-audit-journal-maintenance.timer').get('ActiveState') == 'active'
            and all(unit('jason-audit-journal-maintenance.service').get(k) == v
                    for k,v in (('ActiveState','inactive'),('Result','success'),('ExecMainStatus','0'))))


def protected_health():
    # Authoritative root file, not the writable mirrored readback.
    audit = read(AUDIT, 0, 0o444)
    row = json.loads(audit)
    need(forward_audit_accepted(row) and audit_recovery_service_complete(),
         'AUDIT_FORWARD_RECOVERY_NOT_ACCEPTED')
    controls = control_bytes()
    need(SOURCE.is_symlink() and os.readlink(SOURCE) == SOURCE_TARGET
         and git(SOURCE, 'rev-parse', 'HEAD').decode().strip() == ACCEPTED_SOURCE
         and not git(SOURCE, 'status', '--porcelain', '--untracked-files=all').strip(),
         'SHARED_SOURCE_CHANGED')
    engineering = unit('jason-pmv4-engineering.service', user=True)
    need(engineering.get('ActiveState') == 'inactive' and engineering.get('MainPID') == '0',
         'ENGINEERING_NOT_QUIESCENT')
    need(Path('/opt/jason/current').resolve(strict=True).name == ROLLBACK, 'LKG_POINTER_CHANGED')
    control = json.loads(read(MANAGER / 'production-control-state.json', 0, 0o600))
    manifest = control['last_known_good']['manifest']
    breaker = control['circuit_breaker']
    need(manifest.get('complete') is True and all(manifest.get(k) == ROLLBACK for k in
         ('revision', 'runtime_revision', 'mcp_revision', 'host_revision'))
         and breaker.get('state') == 'closed' and breaker.get('revalidated_revision') == ROLLBACK,
         'NATIVE_BREAKER_OR_LKG_UNVERIFIED')
    desired = read(DESIRED, 0, 0o600)
    need(manifest.get('desired_state_policy_digest') == 'sha256:' + digest(read(Path('/opt/jason/current/config/production-desired-state.json'), 0)), 'LKG_DESIRED_POLICY_MISMATCH')
    native = Path('/opt/jason/current/tools/production_drift_guard.py')
    need(digest(read(native, 0)) == PINNED[str(native)], 'NATIVE_DRIFT_EVALUATOR_CHANGED')
    # Read-only evaluation; no output file, transition, or breaker mutation.
    drift = json.loads(command(['/usr/bin/python3', str(native), '--config', str(DESIRED)], timeout=75))
    need(drift.get('schema_version') == '1.0' and drift.get('status') == 'pass'
         and drift.get('problems') == [], 'NATIVE_DRIFT_NOT_CLEAR')
    peers = {}
    for name in PEERS:
        data = json.loads(command(['/usr/bin/docker', 'inspect', '--type', 'container', name], timeout=18))
        need(len(data) == 1 and data[0]['Name'] == '/' + name, 'PROTECTED_PEER_UNKNOWN')
        d = data[0]; state = d['State']
        need(state.get('Running') is True and (state.get('Health') or {}).get('Status') in
             ('healthy', None), 'PROTECTED_PEER_UNHEALTHY:' + name)
        peers[name] = {'id': d['Id'], 'image': d['Image'], 'started_at': state['StartedAt']}
    need(peers['jason-runtime']['image'] == manifest.get('runtime_image_id')
         and peers['jason-mcp-pilot']['image'] == manifest.get('mcp_image_id'), 'LKG_IMAGE_MISMATCH')
    # Same existing native guard, invoked as the service account; no provider
    # action and no full audit-database scan.
    guard = Path('/opt/jason/independent-component-release/trusted/tools/pmv4_host_release_guard.py')
    need(digest(read(guard, 0, 0o444)) == PINNED[str(guard)], 'CORE_HEALTH_GUARD_CHANGED')
    probe = ("import json,sys; from pathlib import Path; p=Path(sys.argv[1]); "
             "n={'__name__':'native_core_probe','__file__':str(p)}; "
             "exec(compile(p.read_bytes(),str(p),'exec'),n); "
             "print(json.dumps(n['IndependentHostGuard']().core_health_evidence()))")
    core = json.loads(command([*USER, '/usr/bin/python3', '-I', '-B', '-c', probe, str(guard)], timeout=60))
    need(core.get('status') == 'verified' and core.get('source_sha') == ROLLBACK
         and core.get('worker_scan_fresh') is True, 'LIVE_CORE_HEALTH_UNVERIFIED')
    for name, max_age in (('operational-health.json', 600), ('operational-full-health.json', 30*3600)):
        path = SPOOL.parent / name
        health = json.loads(read(path, 1000, 0o600))
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        need(0 <= age <= max_age and health.get('status') == 'pass'
             and health.get('failures') == [] and health.get('snapshot_source_exit_code') == 0
             and health.get('provider_contacted') is False and health.get('provider_credentials_used') is False,
             'AUTHORITY_PROOF_UNVERIFIED:' + name)
        if name == 'operational-health.json':
            need(health.get('full_proof_status') == 'pass' and type(health.get('full_proof_age_seconds')) is int
                 and 0 <= health['full_proof_age_seconds'] <= 30*3600, 'AUTHORITY_FULL_PROOF_UNVERIFIED')
        else:
            proof = health.get('backup_restore_proof', {})
            need(proof.get('counts_match') is True and proof.get('backup_integrity') == 'ok'
                 and proof.get('restore_integrity') == 'ok', 'AUTHORITY_RESTORE_UNVERIFIED')
    return {'protected_peers': peers, 'controls': controls, 'desired_sha256': digest(desired),
            'audit_acceptance_sha256': digest(audit), 'runtime_revision': ROLLBACK}


def rename_noreplace(directory_fd, source, target):
    """Linux atomic no-clobber publish; no transient two-link target."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    need(rename is not None, 'ATOMIC_NOREPLACE_UNAVAILABLE')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory_fd, os.fsencode(source), directory_fd, os.fsencode(target), 1):
        code = ctypes.get_errno() or errno.EIO
        raise OSError(code, os.strerror(code))


class FileSet:
    """Only the fixed allowlist; no following aliases, no broad host installer."""
    def __init__(self, base, uid, gid):
        self.base, self.uid, self.gid = Path(base), uid, gid
        need(self.base.resolve(strict=True) == self.base, 'DESTINATION_ALIAS')
        self.fd = os.open(self.base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        m = os.fstat(self.fd)
        if (m.st_uid, m.st_gid) != (uid, gid) or m.st_mode & 0o022:
            os.close(self.fd)
            raise PermissionError('PARALLEL_COMPONENT_DESTINATION_CUSTODY')

    def __enter__(self): return self
    def __exit__(self, *args): os.close(self.fd)

    def verify_dir(self):
        m = os.stat(self.base, follow_symlinks=False)
        f = os.fstat(self.fd)
        need((m.st_dev, m.st_ino) == (f.st_dev, f.st_ino) and stat.S_ISDIR(m.st_mode)
             and (m.st_uid, m.st_gid) == (self.uid, self.gid) and not m.st_mode & 0o022,
             'DESTINATION_DIRECTORY_CHANGED')

    def snapshot(self, name):
        need(name in FILES, 'DESTINATION_NOT_ALLOWLISTED')
        self.verify_dir()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'rb') as f:
            m = os.fstat(f.fileno())
            need(stat.S_ISREG(m.st_mode) and (m.st_uid,m.st_gid)==(self.uid,self.gid)
                 and m.st_nlink == 1 and not m.st_mode & 0o022
                 and 0 < m.st_size <= 2000000, 'DESTINATION_FILE_CUSTODY:' + name)
            raw = f.read(2000001)
            need(len(raw) == m.st_size, 'DESTINATION_FILE_CHANGED:' + name)
        return raw, stat.S_IMODE(m.st_mode)

    def temp_name(self, name, value):
        need(name in FILES and value is not None, 'TEMPORARY_TARGET_INVALID')
        return '.parallel-reviewed-' + name + '-' + digest(value[0]) + '.tmp'

    def check_temps(self, before, after, *, cleanup=False):
        # Deterministic names are reserved by the exact recorded transaction.
        # Recover only an exact complete staged image, or a Root-owned partial
        # prefix left before ownership transfer. Never delete a foreign file.
        for name in FILES:
            for value in (before[name], after[name]):
                if value is None:
                    continue
                temp = self.temp_name(name, value)
                try:
                    fd = os.open(temp, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
                except FileNotFoundError:
                    continue
                with os.fdopen(fd, 'rb') as f:
                    m = os.fstat(f.fileno())
                    raw = f.read(len(value[0]) + 1)
                    trusted = stat.S_ISREG(m.st_mode) and m.st_nlink == 1 and not m.st_mode & 0o022
                    complete = (m.st_uid,m.st_gid) == (self.uid,self.gid) and raw == value[0]
                    partial = m.st_uid == m.st_gid == 0 and stat.S_IMODE(m.st_mode) == 0o600 and value[0].startswith(raw)
                    need(cleanup and trusted and (complete or partial), 'FOREIGN_OR_UNAPPROVED_TEMPORARY_FILE')
                    current = os.stat(temp, dir_fd=self.fd, follow_symlinks=False)
                    need((current.st_dev,current.st_ino)==(m.st_dev,m.st_ino), 'TEMPORARY_FILE_CHANGED')
                os.unlink(temp, dir_fd=self.fd)
                os.fsync(self.fd)

    def write(self, name, expected, desired):
        need(self.snapshot(name) == expected, 'DESTINATION_BEFORE_IMAGE_CHANGED:' + name)
        if desired is None:
            os.unlink(name, dir_fd=self.fd)
        else:
            temp = self.temp_name(name, desired)
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self.fd)
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(desired[0]); f.flush()
                    os.fchown(f.fileno(), self.uid, self.gid)
                    os.fchmod(f.fileno(), desired[1]); os.fsync(f.fileno())
                need(self.snapshot(name) == expected, 'DESTINATION_RACE:' + name)
                if expected is None:
                    rename_noreplace(self.fd, temp, name)
                else:
                    os.replace(temp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            finally:
                try: os.unlink(temp, dir_fd=self.fd)
                except FileNotFoundError: pass
        os.fsync(self.fd)
        need(self.snapshot(name) == desired, 'DESTINATION_READBACK_CHANGED:' + name)

    def all(self):
        return {name: self.snapshot(name) for name in FILES}

    def rollback(self, before, after):
        # Refuse foreign bytes; restore only this exact reviewed transaction.
        current = self.all()
        need(all(current[name] in (before[name], after[name]) for name in FILES), 'FOREIGN_ROLLBACK_TARGET')
        self.check_temps(before, after, cleanup=True)
        for name in reversed(tuple(FILES)):
            if current[name] != before[name]:
                self.write(name, after[name], before[name])
        need(self.all() == before, 'ROLLBACK_READBACK_FAILED')


def image(value):
    if value is None: return {'state': 'absent'}
    return {'state': 'present', 'sha256': digest(value[0]), 'mode': oct(value[1]), 'bytes': len(value[0])}


def encoded(values):
    return {name: None if value is None else [base64.b64encode(value[0]).decode(), value[1]]
            for name, value in values.items()}


def decoded(values):
    need(set(values) == set(FILES), 'ROLLBACK_FILE_SET_INVALID')
    return {name: None if value is None else (base64.b64decode(value[0], validate=True), value[1])
            for name, value in values.items()}


def scope(candidate, before, after, dependencies, protected, source_hashes):
    need(exact_sha(candidate) and candidate != ROLLBACK, 'CANDIDATE_INVALID')
    need(set(before) == set(after) == set(FILES), 'COMPONENT_FILE_SET_INVALID')
    return {'schema_version': '1.0', 'action': ACTION, 'component': 'development-admission',
            'policy': {'candidate_sha': candidate, 'rollback_sha': ROLLBACK},
            'installation_targets': [str(BASE / n) for n in FILES] + [str(RECORDS / candidate)],
            'before': {n: image(before[n]) for n in FILES}, 'after': {n: image(after[n]) for n in FILES},
            'reserved_temporary_files': sorted({str(BASE / ('.parallel-reviewed-' + n + '-' + digest(v[0]) + '.tmp'))
                for n in FILES for v in (before[n], after[n]) if v is not None}),
            'existing_dependency_sha256': dependencies, 'reviewed_source_sha256': source_hashes,
            'protected': protected, 'shared_source_revision': ACCEPTED_SOURCE, 'shared_source_target': SOURCE_TARGET,
            'queue_cutover': False, 'standing_authority': False, 'provider_writes': False,
            'production_service_restart': False, 'freeze_or_pause_change': False}


def inspect(candidate, fs):
    code, policies = source_and_ci(candidate)
    recheck_overlaps(candidate)
    need(SOURCE.is_symlink() and os.readlink(SOURCE) == SOURCE_TARGET
         and git(SOURCE, 'rev-parse', 'HEAD').decode().strip() == ACCEPTED_SOURCE
         and not git(SOURCE, 'status', '--porcelain', '--untracked-files=all').strip(), 'SHARED_SOURCE_CHANGED')
    dependencies = {}
    for name in DEPS:
        raw = read(BASE / name, 1000)
        need(raw == code['tools/' + name] == git(REPO, 'show', ROLLBACK + ':tools/' + name),
             'DEPENDENCY_CHANGED:' + name)
        dependencies[name] = digest(raw)
    before = fs.all()
    need(before[WORKER] == (git(REPO, 'show', ROLLBACK + ':tools/' + WORKER), 0o700)
         and all(before[n] is None for n in FILES if n != WORKER), 'INSTALL_BASELINE_CHANGED')
    after = {n: (code[path], mode) for n, (path, mode) in FILES.items()}
    fs.check_temps(before, after)
    protected = protected_health()
    head = command([*USER, '/usr/bin/git', 'ls-remote', REMOTE, 'refs/heads/main']).decode().split()
    need(len(head) == 2 and exact_sha(head[0]) and head[1] == 'refs/heads/main',
         'PROTECTED_MAIN_RECHECK_UNAVAILABLE')
    check_newer_paths(git_paths(REPO, candidate, head[0]), policies)
    reviewed = scope(candidate, before, after, dependencies, protected,
                     {name: digest(raw) for name, raw in code.items()})
    need(not os.path.lexists(RECORDS / candidate), 'ONE_USE_INSTALL_ALREADY_RECORDED')
    return reviewed, before, after


def record(directory, name, value):
    raw = canon(value) + b'\n'
    fd = os.open(directory / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    fd = os.open(directory, os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def root_dir(path, create=False):
    if create and not os.path.lexists(path):
        path.mkdir(mode=0o700)
        sync_directory(path.parent)
    m = path.lstat()
    need(path.resolve() == path and stat.S_ISDIR(m.st_mode) and m.st_uid == m.st_gid == 0
         and stat.S_IMODE(m.st_mode) == 0o700, 'RECEIPT_DIRECTORY_CUSTODY')


ACCEPTANCE = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import owner_approved_development_worker as w
import dependency_conflict_service as d
path=w.reviewed_claim_scope_path(Path('/nonexistent-shared-source'))
scopes=d.load_claim_scopes(path)
def item(n): return {'id':'DEV-'+str(n),'issue_number':n,'approval_source':'isolated-canary','approved_by':'isolated-canary'}
state={'items':{}}
selected=d.plan_worker_claims(state,[item(1069),item(1545),item(759)],scopes,capacity=3,production_healthy=True)
assert selected==['DEV-1069','DEV-1545']
assert state['dependency_admission']['queue']['DEV-759']['state']=='blocked_by_dependency'
assert state['dependency_admission']['production_authority'] is False
state={'items':{}}
assert d.plan_worker_claims(state,[item(1545)],scopes,capacity=1,production_healthy=False)==[]
print('INSTALLED_COMPONENT_ISOLATED_CLAIM_ACCEPTANCE=PASS')
"""


def verify_installed():
    result = command([*USER, '/usr/bin/python3', '-I', '-B', '-c', ACCEPTANCE, str(BASE)], timeout=30)
    need(result.strip() == b'INSTALLED_COMPONENT_ISOLATED_CLAIM_ACCEPTANCE=PASS', 'INSTALLED_CANARY_FAILED')


def apply(candidate, ns, fs, expected):
    # Approval is requested only after full preflight. Release lock is then
    # reacquired and the exact material scope is independently recomputed.
    actor = ns['owner'](expected)
    with ns['locks']():
        again, before, after = inspect(candidate, fs)
        need(again == expected, 'APPROVED_MATERIAL_SCOPE_CHANGED')
        root_dir(RECORDS.parent); root_dir(RECORDS, create=True)
        directory = RECORDS / candidate
        directory.mkdir(mode=0o700)
        sync_directory(RECORDS)
        record(directory, 'approval.json', {'scope': again, 'scope_sha256': digest(canon(again)),
               'owner_oid': actor, 'approved_at': stamp(), 'before_bytes': encoded(before),
               'after_bytes': encoded(after), 'rollback_authorized': True})
        try:
            for name in FILES:
                fs.write(name, before[name], after[name])
            verify_installed()
            need(fs.all() == after and protected_health() == again['protected']
                 and {n: digest(read(BASE / n, 1000)) for n in DEPS} == again['existing_dependency_sha256'],
                 'ISOLATED_COMPONENT_POSTFLIGHT_FAILED')
        except BaseException:
            fs.rollback(before, after)
            record(directory, 'result.json', {'status': 'rolled_back', 'at': stamp(),
                   'scope_sha256': digest(canon(again))})
            raise
        record(directory, 'result.json', {'status': 'installed_isolated_verified', 'at': stamp(),
               'scope_sha256': digest(canon(again)), 'live_scheduler_unpaused': False})
    print('PARALLEL_COMPONENT_INSTALL_AND_ISOLATED_ACCEPTANCE=PASS')


def recover(candidate, ns, fs):
    # A crash after the durable Owner decision can restore the exact approved
    # before images, but can never replay installation or overwrite foreign state.
    with ns['locks']():
        root_dir(RECORDS.parent); root_dir(RECORDS); directory = RECORDS / candidate; root_dir(directory)
        need(not os.path.lexists(directory / 'result.json'), 'FINAL_RECEIPT_ALREADY_EXISTS')
        receipt = json.loads(read(directory / 'approval.json', 0, 0o600))
        reviewed = receipt['scope']
        need(reviewed['reviewed_source_sha256']['tools/parallel_development_install.py'] == digest(Path(__file__).read_bytes())
             and reviewed['action'] == ACTION and reviewed['policy'] == {'candidate_sha': candidate, 'rollback_sha': ROLLBACK}
             and receipt['scope_sha256'] == digest(canon(reviewed)) and receipt.get('rollback_authorized') is True
             and bool(receipt.get('owner_oid')) and control_bytes() == reviewed['protected']['controls']
             and unit('jason-pmv4-engineering.service', user=True).get('ActiveState') == 'inactive',
             'RECOVERY_SCOPE_OR_PAUSE_CHANGED')
        before, after = decoded(receipt['before_bytes']), decoded(receipt['after_bytes'])
        need({n: image(before[n]) for n in FILES} == reviewed['before']
             and {n: image(after[n]) for n in FILES} == reviewed['after'], 'RECOVERY_IMAGE_MISMATCH')
        fs.rollback(before, after)
        record(directory, 'result.json', {'status': 'rolled_back_interrupted', 'at': stamp(),
               'scope_sha256': receipt['scope_sha256']})
    print('PARALLEL_COMPONENT_APPROVED_ROLLBACK=PASS')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-sha', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--review-only', action='store_true')
    group.add_argument('--apply', action='store_true')
    group.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    need(os.geteuid() == 0 and sys.flags.isolated == 1 and exact_sha(args.candidate_sha),
         'ISOLATED_ROOT_EXACT_CANDIDATE_REQUIRED')
    need(REPO.parent == Path('/srv/jason/archive/engineering-worktrees'), 'REVIEWED_WORKTREE_REQUIRED')
    # Test the audit gate before any long scans or authentication prompts.
    if not args.recover:
        audit = json.loads(read(AUDIT, 0, 0o444))
        need(forward_audit_accepted(audit) and audit_recovery_service_complete(),
             'AUDIT_FORWARD_RECOVERY_NOT_ACCEPTED')
    ns = native_code(REPO / 'tools/pmv4_e_dispatch_install.py', 'tools/pmv4_e_dispatch_install.py', 1000)
    with FileSet(BASE, 1000, 1000) as fs:
        if args.recover:
            recover(args.candidate_sha, ns, fs)
            return
        with ns['locks']():
            reviewed, _, _ = inspect(args.candidate_sha, fs)
        print(json.dumps({'status': 'scope_reviewed_not_deployment_approved', 'scope': reviewed,
                          'scope_sha256': digest(canon(reviewed)), 'deployment_authorized': False}, sort_keys=True))
        if args.apply:
            apply(args.candidate_sha, ns, fs, reviewed)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('DENIED:' + type(exc).__name__ + ':' + str(exc), file=sys.stderr)
        raise SystemExit(2)
