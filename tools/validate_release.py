#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from release_validation import ReleaseValidationError, ReleaseValidator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the governed Jason release validation foundation."
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of tools/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validator = ReleaseValidator(args.repository)

    print("=== JASON RELEASE VALIDATION ===")

    try:
        results = validator.validate()
    except ReleaseValidationError as error:
        result = error.result
        print(f"FAIL  {result.step_id}: {result.description}")
        if result.output.strip():
            print(result.output.rstrip())
        return 1

    for result in results:
        print(f"PASS  {result.step_id}: {result.description}")
        if result.output.strip():
            print(result.output.rstrip())

    print()
    print("Release validation status: APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
