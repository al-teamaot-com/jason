#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = REPOSITORY_ROOT / "implementation" / "runtime_service" / "src"
if str(RUNTIME_SOURCE) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SOURCE))

from jason_runtime.provider_read_credentials import (
    DEFAULT_RUNTIME_GID,
    DEFAULT_RUNTIME_HOST_ROOT,
    DEFAULT_RUNTIME_UID,
    build_provider_read_specs,
    preflight_provider_read_runtime_credentials,
    stage_provider_read_runtime_credentials,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or locally stage IT Glue and Autotask read-only OpenBao "
            "AppRole bootstrap files for the non-root Jason Runtime container. "
            "Credential values are never printed or hashed."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--stage", action="store_true")
    parser.add_argument("--runtime-uid", type=int, default=DEFAULT_RUNTIME_UID)
    parser.add_argument("--runtime-gid", type=int, default=DEFAULT_RUNTIME_GID)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help=(
            "Allow atomic replacement of already-staged runtime files. "
            "This is intentionally not the default."
        ),
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        help="Optional path for sanitized staging evidence; credential values are excluded.",
    )
    return parser


def _safe_paths() -> dict[str, str]:
    specs = build_provider_read_specs()
    result: dict[str, str] = {}
    for item in specs:
        key = (
            f"JASON_{item.provider.upper()}_OPENBAO_"
            f"{item.credential_name.upper()}_HOST_PATH"
        )
        result[key] = str(item.destination)
    return result


def _write_evidence(path: Path, evidence: dict[str, object]) -> None:
    destination = path.expanduser().resolve()
    if destination.exists():
        raise FileExistsError("evidence output already exists; overwrite is denied")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    destination.chmod(0o600)


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.replace_existing and not args.stage:
        raise PermissionError("--replace-existing is valid only with explicit --stage")

    specs = build_provider_read_specs()
    if args.check_only:
        evidence = preflight_provider_read_runtime_credentials(specs=specs)
        evidence.update(
            {
                "runtime_uid": args.runtime_uid,
                "runtime_gid": args.runtime_gid,
                "runtime_host_root": str(DEFAULT_RUNTIME_HOST_ROOT),
                "compose_host_paths": _safe_paths(),
                "stage_performed": False,
            }
        )
    else:
        evidence = stage_provider_read_runtime_credentials(
            specs=specs,
            runtime_uid=args.runtime_uid,
            runtime_gid=args.runtime_gid,
            replace_existing=args.replace_existing,
        )
        evidence.update(
            {
                "runtime_host_root": str(DEFAULT_RUNTIME_HOST_ROOT),
                "compose_host_paths": _safe_paths(),
                "stage_performed": True,
            }
        )

    if args.evidence_output:
        _write_evidence(args.evidence_output, evidence)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        evidence = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    if args.check_only:
        print("APPROVED: provider runtime credential staging preflight passed; no credential content was read and no files changed.")
    else:
        print("APPROVED: provider runtime credential files staged locally; no provider or OpenBao request was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
