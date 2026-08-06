#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
CLI_SOURCE = IMPLEMENTATION_ROOT / "cli" / "src"
CAPABILITY_SOURCE = IMPLEMENTATION_ROOT / "cap-001" / "src"

for source in (IMPLEMENTATION_ROOT, CLI_SOURCE, CAPABILITY_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.autotask.live_read import (
    AutotaskLiveReadRequest,
    GovernedAutotaskLiveRead,
)
from jason_cap_001.secret_provider_readiness import require_deployment_ready
from jason_cli.runtime import build_autotask_connector


DEFAULT_DEPLOYMENT_RECORD = Path(
    "07-Operations/Jason-Secret-Provider-Deployment-Record.md"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one governed CAP-001 Autotask live read through the "
            "canonical connector and autotask.readonly secret contract."
        )
    )
    parser.add_argument("--ticket-number", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--allowed-scope", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument(
        "--deployment-record",
        type=Path,
        default=DEFAULT_DEPLOYMENT_RECORD,
    )
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def validate_configuration(args: argparse.Namespace) -> None:
    required = {
        "ticket-number": args.ticket_number,
        "scope": args.scope,
        "allowed-scope": args.allowed_scope,
        "principal-id": args.principal_id,
        "organization-id": args.organization_id,
        "correlation-id": args.correlation_id,
    }
    missing = sorted(
        name for name, value in required.items() if not str(value).strip()
    )
    if missing:
        raise ValueError("Required values are blank: " + ", ".join(missing))
    if args.scope.strip() != args.allowed_scope.strip():
        raise PermissionError(
            "Requested scope does not match the authorized scope."
        )
    destination = args.evidence_output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            "Evidence output already exists; overwrite is denied."
        )
    record = args.deployment_record.expanduser().resolve()
    if not record.is_file():
        raise FileNotFoundError(
            "Canonical secret-provider deployment record was not found."
        )
    if args.check_only and args.live_read:
        raise PermissionError(
            "Check-only and live-read modes cannot be requested together."
        )


def run(args: argparse.Namespace) -> Path | None:
    validate_configuration(args)
    if args.check_only:
        return None
    if not args.live_read:
        raise PermissionError(
            "Live read requires the explicit --live-read acknowledgement."
        )

    require_deployment_ready(args.deployment_record)
    service = GovernedAutotaskLiveRead(build_autotask_connector())
    service.validate(
        AutotaskLiveReadRequest(
            ticket_number=args.ticket_number,
            scope_name=args.scope,
            allowed_scope=args.allowed_scope,
            principal_id=args.principal_id,
            organization_id=args.organization_id,
            correlation_id=args.correlation_id,
            live_read_acknowledged=True,
        ),
        output_path=args.evidence_output,
        repository_root=REPOSITORY_ROOT,
    )
    return args.evidence_output.expanduser().resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")

    if args.check_only:
        print(
            "APPROVED: Canonical Autotask live-read configuration validated; "
            "no secret resolved and no OpenBao or Autotask request made."
        )
    else:
        print("APPROVED: Canonical read-only Autotask validation completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
