#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from recovery_package import (
    RecoveryPackageBuilder,
    RecoveryPackageError,
)
from release_validation import (
    ReleaseValidationError,
    ReleaseValidator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a verified Jason recovery package.",
    )
    parser.add_argument("version", help="Release version, such as v0.2.0")
    parser.add_argument("release_name", help="Human-readable release name")
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / "Jason-Recovery",
        help="Recovery package root directory",
    )
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref represented by the recovery package",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip release validation; intended only for focused testing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository_root = Path(__file__).resolve().parents[1]

    if not args.skip_validation:
        print("=== JASON RELEASE VALIDATION ===")
        try:
            results = ReleaseValidator(repository_root).validate()
        except ReleaseValidationError as error:
            result = error.result
            print(f"FAIL  {result.step_id}: {result.description}")
            if result.output:
                print(result.output.rstrip())
            return 1

        for result in results:
            print(f"PASS  {result.step_id}: {result.description}")
        print("Release validation status: APPROVED")

    print("\n=== CREATE RECOVERY PACKAGE ===")
    try:
        result = RecoveryPackageBuilder(
            repository_root,
            args.destination,
        ).build(
            args.version,
            release_name=args.release_name,
            ref=args.ref,
        )
    except (RecoveryPackageError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1

    print(f"Version: {result.version}")
    print(f"Commit: {result.commit}")
    print(f"Destination: {result.destination}")
    for artifact in result.artifacts:
        print(
            f"PASS  {artifact.name} "
            f"({artifact.size_bytes} bytes, {artifact.sha256})"
        )
    print("Recovery package status: VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
