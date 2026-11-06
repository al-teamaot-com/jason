#!/usr/bin/env python3
"""Stage exactly two inert provider-shadow units via the native root release.

This is NOT a standalone deployment or activation mechanism. Only the native
release transaction may invoke the fixed-path root CLI with an exact SHA.
The unit definitions are release-owned, installed disabled, and subject to the
existing candidate-only unit delta rollback planner.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

SHA = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_ROOT = Path('/opt/jason/releases')
INSTALLED_ROOT = Path('/etc/systemd/system')
UNITS = (
    'jason-isolated-provider-health.service',
    'jason-isolated-provider-health.timer',
)
SOURCE_ROOT = Path('infrastructure/openclaw-operations/systemd')
MAX_UNIT_BYTES = 16384
EXEC_START = ('ExecStart=/usr/bin/python3 '
              '/opt/jason/current/tools/isolated_service_shadow.py '
              '--service provider_health_monitor --repo /opt/jason/current '
              '--state-root /var/lib/jason-isolated-services '
              '--provider-source /var/lib/jason/provider-health-canaries.json')
REQUIRED_SOURCE_FILES = (
    'tools/isolated_service_shadow.py',
    'tools/isolated_service_common.py',
    'tools/isolated_service_live_sources.py',
    'tools/isolated_service_github_sources.py',
    'tools/documentation_assurance_service.py',
    'tools/provider_health_monitor_service.py',
    'tools/test_evidence_collection_service.py',
    'tools/work_reconciliation_service.py',
    'tools/dependency_conflict_service.py',
    'tools/source_baseline_monitor_service.py',
    'tools/rollback_readiness_service.py',
    'tools/operational_acceptance_service.py',
    'config/isolated-services.json',
)


class StageError(ValueError):
    pass


def exact_file(path: Path, *, maximum: int = MAX_UNIT_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise StageError('immutable staged source missing or not a regular file')
    if path.stat().st_size < 1 or path.stat().st_size > maximum:
        raise StageError('staged source outside size bound')
    return path.read_bytes()


def pinned_release(path: Path, expected_sha: str, root: Path = RELEASE_ROOT) -> Path:
    if not SHA.fullmatch(expected_sha):
        raise StageError('exact 40-byte hexadecimal candidate SHA required')
    if path.is_symlink() or root.is_symlink() or path.name != expected_sha:
        raise StageError('release identity or root is not an immutable exact SHA')
    actual = path.resolve(strict=True)
    root_actual = root.resolve(strict=True)
    if actual.parent != root_actual or actual.name != expected_sha:
        raise StageError('candidate must be exact immutable native release-root child')
    return actual


def plan_stage(release: Path, installed: Path) -> dict[str, bytes]:
    """Validate all source/policy conditions before touching installed units."""
    cfg = release / 'config/production-desired-state.json'
    policy = json.loads(exact_file(cfg, maximum=65536))
    if policy.get('schema_version') != '1.0':
        raise StageError('unexpected desired-state schema')
    allowed = policy.get('allowed_system_units')
    required = policy.get('required_system_units')
    if not isinstance(allowed, list) or not isinstance(required, list):
        raise StageError('missing native desired-state unit lists')
    if not set(UNITS).issubset(set(allowed)) or set(UNITS) & set(required):
        raise StageError('shadow units must be only allowed, never required')
    inventory = json.loads(exact_file(release / 'infrastructure/isolated-services/installation-manifest.json', maximum=65536))
    phase = inventory.get('staged_native_provider_shadow')
    if not isinstance(phase, dict) or phase.get('deployment_phase') != 'stage_disabled_only':
        raise StageError('explicit disabled-stage inventory missing')
    if (phase.get('requires_production_exact_sha_authorization') is not True or
            phase.get('allows_service_or_timer_activation') is not False or
            phase.get('rollback_bound_increment') != 2):
        raise StageError('stage does not preserve native authorization/rollback boundaries')
    declared = phase.get('unit_sources')
    if not isinstance(declared, list) or set(declared) != {str(SOURCE_ROOT / u) for u in UNITS}:
        raise StageError('immutable stage inventory does not match exactly two units')
    for name in REQUIRED_SOURCE_FILES:
        exact_file(release / name, maximum=524288)
    plan: dict[str, bytes] = {}
    for name in UNITS:
        plan[name] = exact_file(release / SOURCE_ROOT / name)
    service = plan[UNITS[0]].decode('utf-8')
    timer = plan[UNITS[1]].decode('utf-8')
    if (service.count('ExecStart=') != 1 or EXEC_START not in service or
            not all(rule in service for rule in ('Type=oneshot', 'User=al',
                    'ProtectSystem=strict','NoNewPrivileges=true',
                    'WorkingDirectory=/opt/jason/current',
                    'ConditionPathExists=/var/lib/jason/provider-health-canaries.json'))):
        raise StageError('provider shadow is not the fixed read-only worker contract')
    if any(x in service for x in ('ExecStartPre=', 'ExecStop=', 'ExecReload=', 'ExecCondition=',
                                 'sudo ', '/home/al/projects/', '/home/al/jason-worktrees/')):
        raise StageError('unsafe provider shadow execution hook or developer path')
    if ('Unit=jason-isolated-provider-health.service' not in timer or
            'WantedBy=timers.target' not in timer or
            any(x in timer for x in ('ExecStart=', 'OnCalendar=*-*-* *:*:*'))):
        raise StageError('invalid disabled provider shadow timer contract')
    if installed.is_symlink() or not installed.is_dir():
        raise StageError('installed systemd destination is not a directory')
    for name, data in plan.items():
        target = installed / name
        if target.is_symlink():
            raise StageError('existing installed unit is a symlink')
        if target.exists():
            if not target.is_file() or not stat.S_ISREG(target.stat().st_mode):
                raise StageError('installed unit not a regular file')
            if target.read_bytes() != data:
                raise StageError('existing unit differs from exact candidate source')
    return plan


def _atomic_install(directory: Path, name: str, data: bytes) -> None:
    """Copy immutable bytes; no enable/start or unrelated unit mutation."""
    fd, temp = tempfile.mkstemp(prefix='.jason-isolated-shadow-', dir=str(directory))
    try:
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, directory / name)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def stage(release: Path, installed: Path) -> tuple[str, ...]:
    plan = plan_stage(release, installed)
    changed = []
    for unit, data in plan.items():
        path = installed / unit
        if path.is_file() and path.read_bytes() == data:
            continue
        _atomic_install(installed, unit, data)
        changed.append(unit)
    return tuple(changed)


def check_dormant(unit: str, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    for probe in ('is-active','is-enabled'):
        result = runner(['systemctl', probe, unit], capture_output=True, text=True, check=False, timeout=10)
        outcome = result.stdout.strip()
        if probe == 'is-active' and outcome not in ('inactive','unknown'):
            raise StageError('shadow unit is active, failed or unexpectedly transitioning')
        if probe == 'is-enabled' and outcome not in ('disabled','static','not-found'):
            raise StageError('shadow unit enabled or masked instead of dormant')


def main() -> int:
    parser=argparse.ArgumentParser(description='Root-only immutable release disabled shadow stage')
    parser.add_argument('--release-dir',type=Path,required=True)
    parser.add_argument('--expected-sha',required=True)
    args=parser.parse_args()
    if os.geteuid() != 0:
        parser.error('native root release transaction required')
    release=pinned_release(args.release_dir,args.expected_sha)
    for unit in UNITS:
        check_dormant(unit)
    # The source/target contract is verified before any file is copied.
    changed=stage(release,INSTALLED_ROOT)
    subprocess.run(['systemctl','daemon-reload'],check=True,timeout=20)
    for unit in UNITS:
        check_dormant(unit)
        if (INSTALLED_ROOT/unit).read_bytes() != (release/SOURCE_ROOT/unit).read_bytes():
            raise StageError('staged unit bytes differ from immutable release')
    print('ISOLATED_PROVIDER_SHADOW_STAGE=DISABLED_VERIFIED')
    print('ISOLATED_PROVIDER_SHADOW_UNIT_COUNT='+str(len(UNITS)))
    print('ISOLATED_PROVIDER_SHADOW_CHANGED_COUNT='+str(len(changed)))
    print('ISOLATED_PROVIDER_SHADOW_PRODUCTION_AUTHORITY=NONE')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
