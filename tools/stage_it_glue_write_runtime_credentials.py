#!/usr/bin/env python3
"""Source-only explicit IT Glue write AppRole staging (root-governed only).

This wrapper reuses the existing credential stage/preflight engine. No credential
bytes are printed, hashed or uploaded; no new runtime permission is granted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "implementation" / "runtime_service" / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from jason_runtime.provider_read_credentials import (
    ProviderRuntimeCredentialSpec,
    preflight_provider_read_runtime_credentials,
    stage_provider_read_runtime_credentials,
)

_BOOTSTRAP = Path("/opt/jason/bootstrap/secrets/openbao/itglue-write-approle")
_STAGED = Path("/run/jason-runtime-credentials/openbao/it-glue-write")
_SPECS = (
    ProviderRuntimeCredentialSpec(
        provider="it_glue_write",
        credential_name="role_id",
        source=_BOOTSTRAP / "role-id",
        destination=_STAGED / "role_id",
    ),
    ProviderRuntimeCredentialSpec(
        provider="it_glue_write",
        credential_name="secret_id",
        source=_BOOTSTRAP / "secret-id",
        destination=_STAGED / "secret_id",
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded root-managed staging of separately approved IT Glue write AppRole"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only", action="store_true")
    group.add_argument("--stage", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.replace_existing and not args.stage:
        raise PermissionError("IT_GLUE_WRITE_REPLACE_REQUIRES_EXPLICIT_STAGE")
    if args.stage:
        result = stage_provider_read_runtime_credentials(
            specs=_SPECS, runtime_uid=1000, runtime_gid=1000,
            replace_existing=args.replace_existing,
        )
    else:
        result = preflight_provider_read_runtime_credentials(specs=_SPECS)
    return {
        "status": "staged" if args.stage else "preflight",
        "provider": "it_glue_write",
        "credential_files": 2,
        "runtime_role_id_host_path": str(_STAGED / "role_id"),
        "runtime_secret_id_host_path": str(_STAGED / "secret_id"),
        "credential_values_disclosed": False,
        "stage_performed": args.stage,
        "stager_result": result,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evidence = run(args)
    except Exception as exc:
        print("DENIED: " + type(exc).__name__)
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
