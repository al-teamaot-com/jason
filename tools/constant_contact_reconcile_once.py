#!/usr/bin/env python3
"""Independently supervised Constant Contact readback cycle, no provider POST.

The reviewed scheduler must invoke one bounded cycle after an explicit
production release. This tool never installs a timer or changes a worker.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

PROFILE_ENV = "JASON_CONSTANT_CONTACT_RECONCILE_PROFILE"
PROFILE = "constant-contact-aot-readback-v1"


def run_cycle(application, *, max_items: int = 25) -> dict[str, object]:
    worker = getattr(application, "constant_contact_reconciliation_worker", None)
    if worker is None:
        raise RuntimeError("Constant Contact readback worker is not activated")
    return asdict(worker.run_once(max_items=max_items))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GET-only Constant Contact reconciliation")
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--check-only", action="store_true")
    choices.add_argument("--run-once", action="store_true")
    parser.add_argument("--max-items", type=int, default=25)
    args = parser.parse_args(argv)
    if not 1 <= args.max_items <= 25:
        parser.error("max-items must be between 1 and 25")
    enabled = os.environ.get(PROFILE_ENV, "") == PROFILE
    if args.check_only:
        print(json.dumps({"mode": "GET-only", "profile_configured": enabled,
                          "run_once_available": True, "executed": False}))
        return 0
    if not enabled:
        print(json.dumps({"status": "disabled", "executed": False}))
        return 2
    # Only an explicitly opted-in, separately supervised process can compose
    # the provider-backed worker. It does not run application maintenance.
    from jason_runtime.composition import RuntimeSettings, build_runtime_application
    application = build_runtime_application(
        RuntimeSettings.from_env(), maintenance_profile="auxiliary",
    )
    result = run_cycle(application, max_items=args.max_items)
    print(json.dumps({"status": "cycle_complete", **result}, sort_keys=True))
    return 0 if result["blocked"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # No provider exception / OAuth / contact data in supervisor stdout.
        print(json.dumps({"status": "failed", "error_code": "readback_cycle_failed"}))
        sys.exit(1)
