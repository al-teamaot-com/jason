#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
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
    p.add_argument("--candidate-sha", default=None)
    p.add_argument("--trigger", default="scheduled")
    return p.parse_args()


_PENDING_SOURCE_CHECKS = frozenset({
    "checker-currentness",
    "runtime-source-alignment",
    "material-change-owner-review",
})
_REQUIRED_SCHEDULED_CHECKS = frozenset({
    "checker-currentness", "runtime-source-alignment", "j002-article-matrix",
    "system-registry", "j900-release-validation",
    "mcp-constitutional-production-equivalent", "systemd-failed-units",
    "prometheus-targets", "openclaw-authority-health", "immutable-runtime-release",
    "mcp-governance-boundary", "governed-provider-boundary-canaries",
})


def _scheduled_source_change_pending(result, config: CCCConfig, *, force: bool, trigger: str) -> bool:
    """Successful *evaluation* of an unshipped change is not CCC certification.

    Never use this exception for forced/release checks, FAIL, missing reports,
    unrelated unhealthy controls, stale checkout, or divergent source history.
    """
    if force or trigger != "scheduled" or result.status != "NOT_PROVEN" or not result.report_path:
        return False
    try:
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
        source = str(result.source_revision or "")
        runtime = str(result.runtime_revision or "")
        if (not re.fullmatch(r"[0-9a-f]{40}", source)
                or not re.fullmatch(r"[0-9a-f]{40}", runtime)
                or source == runtime
                or report.get("status") != "NOT_PROVEN"
                or report.get("trigger") != "material_change"
                or report.get("source_revision") != source
                or report.get("runtime_revision") != runtime):
            return False
        checks = report.get("checks")
        if not isinstance(checks, list) or len(checks) < 12:
            return False
        statuses = {}
        for check in checks:
            if not isinstance(check, dict):
                return False
            key, status = check.get("check_id"), check.get("status")
            if not isinstance(key, str) or not key or key in statuses:
                return False
            if status != "PASS" and (key not in _PENDING_SOURCE_CHECKS or status != "NOT_PROVEN"):
                return False
            statuses[key] = status
        if not _REQUIRED_SCHEDULED_CHECKS.issubset(statuses):
            return False
        pending = {key for key, status in statuses.items() if status != "PASS"}
        if "runtime-source-alignment" not in pending:
            return False
        if (report.get("material_changes") and
                statuses.get("material-change-owner-review") not in {"PASS", "NOT_PROVEN"}):
            return False
        completed = subprocess.run(
            ["git", "-C", str(config.repository_root), "merge-base", "--is-ancestor", runtime, source],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
        return completed.returncode == 0
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    args=parse_args()
    try:
        config=CCCConfig.load(args.config)
        checker_revision=REPO.resolve().name if len(REPO.resolve().name)==40 else ""
        if len(checker_revision)!=40:
            import subprocess
            checker_revision=subprocess.check_output(["git","-C",str(REPO),"rev-parse","HEAD"],text=True).strip()
        result=CCCRunner(config,checker_revision=checker_revision).run(force=args.force,trigger=args.trigger,candidate_sha=args.candidate_sha)
    except (CCCRunnerError, OSError, ValueError) as exc:
        print(f"CCC_STATUS=NOT_PROVEN\nREASON={type(exc).__name__}:{exc}")
        return 2
    print(f"CCC_STATUS={result.status}")
    print(f"CCC_TRIGGER={result.trigger}")
    if result.source_revision: print(f"SOURCE_REVISION={result.source_revision}")
    if result.runtime_revision: print(f"RUNTIME_REVISION={result.runtime_revision}")
    if result.report_path: print(f"REPORT={result.report_path}")
    if result.checkpoint_id: print(f"LAST_KNOWN_COMPLIANT={result.checkpoint_id}")
    if (not args.force and args.trigger == "scheduled" and
            _scheduled_source_change_pending(
                result, config, force=args.force, trigger=args.trigger
            )):
        # The scheduled observer completed successfully, but certification
        # remains NOT_PROVEN, no compliant pointer advances, and no release
        # candidate gains authorization. A separate release CCC must PASS.
        print("CCC_SCHEDULED_EVALUATION=SOURCE_PENDING_NOT_CERTIFIED")
        return 0
    return 0 if result.status in {"PASS","NOT_DUE","DISABLED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
