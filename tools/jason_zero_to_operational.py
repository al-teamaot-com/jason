from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.zero_to_operational import receipt_to_json
from tools.zero_to_operational_synthetic import (
    run_synthetic_zero_to_operational,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    repo = _root()
    parser = argparse.ArgumentParser(
        description="Run Jason Zero-to-Operational acceptance"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    synthetic = sub.add_parser(
        "synthetic",
        help=(
            "exercise the full deployability chain on isolated synthetic "
            "candidate roots; does not prove host deployability"
        ),
    )
    synthetic.add_argument("--workspace", required=True)
    synthetic.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.mode != "synthetic":
        parser.error("unsupported acceptance mode")

    receipt = run_synthetic_zero_to_operational(
        repository_root=repo,
        workspace=args.workspace,
    )
    payload = json.loads(receipt_to_json(receipt))
    schema = json.loads(
        (
            repo
            / "config/schemas/zero-to-operational-receipt.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)

    output = Path(args.output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(
            f"acceptance receipt already exists: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(receipt_to_json(receipt), encoding="utf-8")
    print(json.dumps(
        {
            "status": receipt.status,
            "mode": receipt.mode,
            "deployability_proven": receipt.deployability_proven,
            "production_authorized": receipt.production_authorized,
            "phase_count": len(receipt.phases),
            "receipt_sha256": receipt.receipt_sha256,
            "output": str(output),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0 if receipt.status == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
