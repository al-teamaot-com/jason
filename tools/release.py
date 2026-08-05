#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.release_pipeline import ReleasePipeline, ReleasePipelineError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the governed Jason release pipeline.",
    )
    parser.add_argument("version", help="Release version, such as v0.1.2")
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
        help="Git ref represented by the release",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=== JASON GOVERNED RELEASE PIPELINE ===")
    try:
        result = ReleasePipeline(
            REPOSITORY_ROOT,
            args.destination,
        ).run(
            args.version,
            release_name=args.release_name,
            ref=args.ref,
        )
    except ReleasePipelineError as error:
        print(f"FAIL  {error.stage}: {error}")
        print("Release status: DENIED")
        return 1

    print("PASS  validation: Release validation approved")
    print("PASS  recovery-package: Recovery package created and verified")
    print("PASS  restore-verification: Restored repository validation approved")
    print()
    print("=== JASON RELEASE SUMMARY ===")
    print(f"Version: {result.version}")
    print(f"Release: {result.release_name}")
    print(f"Commit: {result.commit}")
    print(f"Recovery: {result.package_directory}")
    print("Release status: APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
