#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_OUTPUT = Path('/var/lib/jason/openclaw/operational-health.json')
SOURCE_HEALTH_TIMEOUT_SECONDS = 900
SOURCE_HEALTH_TIMEOUT_EXIT_CODE = 124


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
            handle.write('\\n')
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
            [sys.executable, str(tool)],
            capture_output=True,
            text=True,
            check=False,
            # Full PRAGMA integrity_check includes the multi-GB orchestration
            # audit database, plus authority backup/restore verification.
            # Keep the *complete* checks bounded, but do not truncate them.
            timeout=SOURCE_HEALTH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A timeout must not leave a previously successful snapshot looking
        # current: publish explicit failure evidence and exit nonzero.
        report = {
            'status': 'fail',
            'failures': ['operational_health_timeout'],
            'snapshot_source_exit_code': SOURCE_HEALTH_TIMEOUT_EXIT_CODE,
            'snapshot_timeout_seconds': SOURCE_HEALTH_TIMEOUT_SECONDS,
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
    if not completed.stdout.strip():
        raise SystemExit('operational health tool returned no JSON output')

    report = json.loads(completed.stdout)
    report['snapshot_source_exit_code'] = completed.returncode

    write_atomic_snapshot(args.output, report)

    print(json.dumps({
        'status': report.get('status', 'fail'),
        'action': 'openclaw_authority_health_snapshot_written',
        'output': str(args.output),
        'source_exit_code': completed.returncode,
    }, sort_keys=True))
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
