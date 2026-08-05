#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from restore_verification import (
    RecoveryRestoreVerifier,
    RestoreVerificationError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore and validate a Jason recovery package.",
    )
    parser.add_argument(
        "package_directory",
        type=Path,
        help="Recovery package directory to verify",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Optional disposable restore workspace",
    )
    parser.add_argument(
        "--retain-workspace",
        action="store_true",
        help="Retain the restored repository for inspection",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository_root = Path(__file__).resolve().parents[1]

    print("=== JASON RECOVERY RESTORE VERIFICATION ===")
    try:
        result = RecoveryRestoreVerifier(repository_root).verify(
            args.package_directory,
            workspace_root=args.workspace,
            retain_workspace=args.retain_workspace,
        )
    except (RestoreVerificationError, ValueError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1

    print(f"Version: {result.version}")
    print(f"Commit: {result.commit}")
    print(f"Bundle: {result.bundle}")
    if result.validation_output:
        print(result.validation_output.rstrip())
    print("Restore verification status: APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
