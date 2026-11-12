#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_OUTPUT = Path('/var/lib/jason/openclaw/operational-health.json')
LAST_SUCCESS = Path('/var/lib/jason/openclaw/operational-full-health-last-pass.json')
# Full SQLite checks now cover a >28 GB orchestration audit and multi-GB
# authority backup/restore. Retain a strict bound, but allow one 60-minute
# overnight attempt; never convert a timeout into a passing proof.
SOURCE_HEALTH_TIMEOUT_SECONDS = 3600
BACKUP_TEMP_ROOT = Path('/srv/jason/archive')
SOURCE_HEALTH_TIMEOUT_EXIT_CODE = 124

# Stage progress is informational evidence on failure, never a replacement
# for a completed full SQLite integrity + backup/restore proof.
_STAGE_LINE = re.compile(
    r'^JASON_FULL_INTEGRITY_STAGE_V1\|(authority|replay|security_audit|'
    r'authority_backup_restore|orchestration_audit)\|([0-9]{1,7}(?:\.[0-9]{1,3})?)$'
)


def completed_timeout_stages(stderr: bytes | str | None) -> dict[str, float]:
    if not stderr:
        return {}
    raw = stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes) else stderr
    completed: dict[str, float] = {}
    for line in raw.splitlines():
        match = _STAGE_LINE.fullmatch(line.strip())
        if match is not None:
            completed[match.group(1)] = float(match.group(2))
    return completed


def write_atomic_snapshot(output: Path, report: dict[str, object]) -> None:
    """Publish a complete health result without ever exposing a partial file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix='.operational-health-', suffix='.json', dir=output.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, output)
        os.chmod(output, 0o600)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description='Write an atomic secret-safe OpenClaw/JKD-001 operational-health snapshot')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tool = Path(__file__).with_name('openclaw_authority_operational_health.py')
    try:
        completed = subprocess.run(
            [sys.executable, str(tool), '--backup-temp-root', str(BACKUP_TEMP_ROOT)],
            capture_output=True,
            text=True,
            check=False,
            # Full PRAGMA integrity_check includes the multi-GB orchestration
            # audit database, plus authority backup/restore verification.
            # Keep the *complete* checks bounded, but do not truncate them.
            timeout=SOURCE_HEALTH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # A timeout must not leave a previously successful snapshot looking
        # current: publish explicit failure evidence and exit nonzero.
        report = {
            'status': 'fail',
            'failures': ['operational_health_timeout'],
            'snapshot_source_exit_code': SOURCE_HEALTH_TIMEOUT_EXIT_CODE,
            'snapshot_timeout_seconds': SOURCE_HEALTH_TIMEOUT_SECONDS,
            'completed_stage_seconds': completed_timeout_stages(exc.stderr),
            'provider_contacted': False,
            'provider_credentials_used': False,
        }
        write_atomic_snapshot(args.output, report)
        print(json.dumps({
            'status': 'fail',
            'action': 'openclaw_authority_health_snapshot_written',
            'reason': 'operational_health_timeout',
            'source_exit_code': SOURCE_HEALTH_TIMEOUT_EXIT_CODE,
        }, sort_keys=True))
        return SOURCE_HEALTH_TIMEOUT_EXIT_CODE
    except OSError:
        report = {
            'status': 'fail',
            'failures': ['operational_health_launch_error'],
            'provider_contacted': False,
            'provider_credentials_used': False,
        }
        write_atomic_snapshot(args.output, report)
        return 2
    if not completed.stdout.strip():
        # A source exception can exit without producing JSON. Never leave an
        # old PASS as the current full-integrity result.
        report = {
            'status': 'fail',
            'failures': ['operational_health_missing_output'],
            'snapshot_source_exit_code': completed.returncode,
            'provider_contacted': False,
            'provider_credentials_used': False,
        }
        write_atomic_snapshot(args.output, report)
        return completed.returncode if completed.returncode != 0 else 2

    try:
        report = json.loads(completed.stdout)
    except (json.JSONDecodeError, ValueError):
        report = None
    if not isinstance(report, dict):
        report = {
            'status': 'fail',
            'failures': ['operational_health_invalid_json'],
            'snapshot_source_exit_code': completed.returncode,
            'provider_contacted': False,
            'provider_credentials_used': False,
        }
        write_atomic_snapshot(args.output, report)
        return completed.returncode if completed.returncode != 0 else 2
    report['snapshot_source_exit_code'] = completed.returncode
    if completed.returncode != 0:
        # Even a contradictory source response must never publish PASS.
        report['status'] = 'fail'
        failures = report.get('failures')
        if not isinstance(failures, list):
            failures = []
        if 'source_health_nonzero_exit' not in failures:
            failures.append('source_health_nonzero_exit')
        report['failures'] = failures

    write_atomic_snapshot(args.output, report)
    # Keep the last verified PASS separately, so a later timeout cannot erase
    # the proof of a completed scan. Never archive a nonzero/partial result.
    if (report.get('status') == 'pass'
            and completed.returncode == 0
            and report.get('failures') == []
            and report.get('provider_contacted') is False
            and report.get('provider_credentials_used') is False):
        write_atomic_snapshot(LAST_SUCCESS, report)

    print(json.dumps({
        'status': report.get('status', 'fail'),
        'action': 'openclaw_authority_health_snapshot_written',
        'output': str(args.output),
        'source_exit_code': completed.returncode,
    }, sort_keys=True))
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
