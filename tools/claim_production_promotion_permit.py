#!/usr/bin/env python3
"""Verify and atomically consume a trusted Production promotion permit.

The trust registry and claims database are fixed by the deployment contract.
A caller can provide a permit and expected deployment identity but cannot
replace the trust root through CLI arguments.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from orchestrator.production_promotion_permit import verify_and_claim_production_permit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--permit", required=True)
    parser.add_argument("--component", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    permit = verify_and_claim_production_permit(
        permit_path=args.permit,
        component=args.component,
        operation=args.operation,
        source_sha=args.source_sha,
        artifact_digest=args.artifact_digest,
        plan_sha256=args.plan_sha256,
        claim=not args.check_only,
    )
    state = "VERIFIED" if args.check_only else "CLAIMED"
    print(f"PRODUCTION_PROMOTION_PERMIT={state}")
    print(f"PERMIT_ID={permit.permit_id}")
    print(f"APPROVAL_ID={permit.approval_id}")
    print(f"PROMOTION_ID={permit.promotion_id}")
    print(f"PLAN_SHA256={permit.plan_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
