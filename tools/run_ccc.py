#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.ccc_runner import CCCConfig, CCCRunner, CCCRunnerError


def parse_args():
    p=argparse.ArgumentParser(description="Run the deterministic Jason Constitutional and Compliance Check (CCC).")
    p.add_argument("--config", type=Path, default=Path("/etc/jason/ccc.json"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--trigger", default="scheduled")
    return p.parse_args()


def main() -> int:
    args=parse_args()
    try:
        config=CCCConfig.load(args.config)
        checker_revision=REPO.resolve().name if len(REPO.resolve().name)==40 else ""
        if len(checker_revision)!=40:
            import subprocess
            checker_revision=subprocess.check_output(["git","-C",str(REPO),"rev-parse","HEAD"],text=True).strip()
        result=CCCRunner(config,checker_revision=checker_revision).run(force=args.force,trigger=args.trigger)
    except (CCCRunnerError, OSError, ValueError) as exc:
        print(f"CCC_STATUS=NOT_PROVEN\nREASON={type(exc).__name__}:{exc}")
        return 2
    print(f"CCC_STATUS={result.status}")
    print(f"CCC_TRIGGER={result.trigger}")
    if result.source_revision: print(f"SOURCE_REVISION={result.source_revision}")
    if result.runtime_revision: print(f"RUNTIME_REVISION={result.runtime_revision}")
    if result.report_path: print(f"REPORT={result.report_path}")
    if result.checkpoint_id: print(f"LAST_KNOWN_COMPLIANT={result.checkpoint_id}")
    return 0 if result.status in {"PASS","NOT_DUE","DISABLED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
