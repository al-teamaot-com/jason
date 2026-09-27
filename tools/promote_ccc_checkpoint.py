#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.ccc_checkpoint import CCCCheckpointError, LastKnownCompliantPromoter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote a passing CCC result to Last Known Compliant.")
    parser.add_argument("--ccc-report", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path, default=Path.home() / "Jason-Recovery" / "CCC")
    parser.add_argument("--checkpoint-root", type=Path, default=Path.home() / "Jason-Evidence" / "CCC")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = LastKnownCompliantPromoter(
            REPOSITORY_ROOT,
            args.recovery_root,
            args.checkpoint_root,
        ).promote(args.ccc_report, args.runtime_manifest)
    except CCCCheckpointError as error:
        print(f"CCC_LAST_KNOWN_COMPLIANT=DENIED\nREASON={error}")
        return 1
    print("CCC_LAST_KNOWN_COMPLIANT=PASS")
    print(f"CHECKPOINT_ID={result.checkpoint_id}")
    print(f"SOURCE_REVISION={result.source_revision}")
    print(f"RUNTIME_REVISION={result.runtime_revision}")
    print(f"RECOVERY_DIRECTORY={result.recovery_directory}")
    print(f"CHECKPOINT_DIRECTORY={result.checkpoint_directory}")
    print(f"POINTER={result.pointer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
