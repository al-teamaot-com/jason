#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO_ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from kernel.system_registry import VerificationOutcome  # noqa: E402
from kernel.system_registry.manifest import registry_from_manifest  # noqa: E402
from kernel.system_registry.probes import (  # noqa: E402
    HostObservationRunner,
    ProbeExecutionError,
    load_verification_plan,
)


DEFAULT_MANIFEST = (
    REPO_ROOT
    / "implementation/kernel/system_registry/production-registry.json"
)
DEFAULT_PLAN = (
    REPO_ROOT
    / "implementation/kernel/system_registry/production-verification-plan.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Jason's production System Registry and optionally collect "
            "bounded read-only host observations."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate declared topology and the observation plan without probing the host.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = registry_from_manifest(args.manifest)
    plan = load_verification_plan(args.plan, registry=registry)

    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "valid",
                    "registered_entities": len(registry.list_all()),
                    "planned_host_checks": len(plan.checks),
                    "declared_state_changed": False,
                    "remediation_attempted": False,
                },
                sort_keys=True,
            )
        )
        return 0

    observed_at = datetime.now(timezone.utc)
    runner = HostObservationRunner()
    results: list[dict[str, object]] = []
    verified_count = 0

    evidence_reference = None
    if args.output is not None:
        evidence_reference = f"file://{args.output.resolve()}"

    for check in plan.checks:
        try:
            observation = runner.observe(
                check=check,
                source=plan.source,
                observed_at=observed_at,
                evidence_reference=evidence_reference,
            )
            registry.record_observation(observation)
            verification = registry.verify_from_latest_observation(
                registry_id=check.registry_id,
                method=check.method,
                verified_at=observed_at,
            )
            outcome = verification.outcome
            detail = verification.detail
            observed_state = dict(observation.observed_state)
        except ProbeExecutionError as error:
            outcome = VerificationOutcome.FAILED
            detail = str(error)
            observed_state = {}

        if outcome is VerificationOutcome.VERIFIED:
            verified_count += 1
        results.append(
            {
                "registry_id": check.registry_id,
                "method": check.method,
                "outcome": outcome.value,
                "detail": detail,
                "observed_state": observed_state,
            }
        )

    total = len(plan.checks)
    report = {
        "schema_version": "1.0",
        "generated_at": observed_at.isoformat(),
        "manifest": str(args.manifest),
        "verification_plan": str(args.plan),
        "observation_source": plan.source,
        "summary": {
            "registered_entities": len(registry.list_all()),
            "planned_host_checks": total,
            "verified": verified_count,
            "not_verified": total - verified_count,
            "status": "pass" if verified_count == total else "attention-required",
        },
        "results": results,
        "declared_state_changed": False,
        "remediation_attempted": False,
    }

    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(str(args.output))

    return 0 if verified_count == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
