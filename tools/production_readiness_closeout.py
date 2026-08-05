from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Sequence


DEFAULT_RECORD = Path("07-Operations/Jason-Secret-Provider-Deployment-Record.md")


def require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"Required value is blank: {name}")


def require_new_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"Output already exists: {resolved}")
    return resolved


def run_command(command: list[str], *, label: str) -> None:
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed without exposing protected output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the accelerated governed INF-001 readiness closeout sequence."
    )
    parser.add_argument("--ticket-number", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--allowed-scope", required=True)
    parser.add_argument("--username-reference", default="autotask.api.username")
    parser.add_argument("--secret-reference", default="autotask.api.secret")
    parser.add_argument("--integration-code-reference", default="autotask.api.integration-code")
    parser.add_argument("--secret-command", type=Path, default=Path("/usr/local/bin/jason-secret"))
    parser.add_argument("--deployment-record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--contract-evidence", type=Path, required=True)
    parser.add_argument("--autotask-evidence", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--live-read", action="store_true")
    return parser


def validate(args: argparse.Namespace) -> None:
    for name in (
        "ticket_number",
        "company_id",
        "scope",
        "allowed_scope",
        "username_reference",
        "secret_reference",
        "integration_code_reference",
    ):
        require_text(name.replace("_", "-"), str(getattr(args, name)))
    if args.scope.strip() != args.allowed_scope.strip():
        raise PermissionError("Requested scope does not match the authorized scope.")
    require_new_output(args.contract_evidence)
    require_new_output(args.autotask_evidence)
    if not args.secret_command.expanduser().resolve().is_file():
        raise FileNotFoundError("Canonical secret command was not found.")
    if not args.deployment_record.expanduser().resolve().is_file():
        raise FileNotFoundError("Canonical deployment record was not found.")


def execute(args: argparse.Namespace) -> dict[str, object]:
    validate(args)
    if args.check_only:
        return {
            "status": "approved",
            "mode": "check-only",
            "secret_resolved": False,
            "openbao_contacted": False,
            "autotask_contacted": False,
        }

    run_command(
        [
            "sudo",
            ".venv-test/bin/python",
            "tools/provision_openbao_contract_test.py",
            "--evidence-output",
            str(args.contract_evidence),
        ],
        label="OpenBao authenticated contract test",
    )

    autotask_command = [
        ".venv-test/bin/python",
        "tools/autotask_live_read.py",
        "--ticket-number",
        args.ticket_number,
        "--company-id",
        args.company_id,
        "--scope",
        args.scope,
        "--allowed-scope",
        args.allowed_scope,
        "--evidence-output",
        str(args.autotask_evidence),
        "--username-reference",
        args.username_reference,
        "--secret-reference",
        args.secret_reference,
        "--integration-code-reference",
        args.integration_code_reference,
        "--secret-command",
        str(args.secret_command),
        "--deployment-record",
        str(args.deployment_record),
    ]
    if args.live_read:
        autotask_command.append("--live-read")
    else:
        autotask_command.append("--check-only")
    run_command(autotask_command, label="CAP-001 Autotask validation")

    return {
        "status": "approved",
        "mode": "live-read" if args.live_read else "configuration-only",
        "contract_evidence": str(args.contract_evidence.expanduser().resolve()),
        "autotask_evidence": str(args.autotask_evidence.expanduser().resolve()),
        "secret_values_exposed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
