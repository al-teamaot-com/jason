from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Sequence

from .autotask_http_transport import AutotaskCredentialReferences
from .autotask_live_read_validation import (
    AutotaskLiveReadValidator,
    LiveReadValidationRequest,
)
from .autotask_production_transport import build_autotask_ticket_transport
from .autotask_ticket_provider import AutotaskTicketProvider


class CommandSecretBrokerError(RuntimeError):
    """Raised when the configured secret command cannot resolve a secret safely."""


@dataclass(frozen=True, slots=True)
class CommandSecretBroker:
    """Resolve one secret reference through an external broker command.

    The command is executed without a shell and receives the reference as its only
    argument. Secret values are returned in memory and are never logged here.
    """

    executable: Path
    timeout_seconds: float = 10.0
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run

    def get_secret(self, reference: str) -> str:
        normalized_reference = reference.strip()
        if not normalized_reference:
            raise CommandSecretBrokerError("Secret reference must be non-empty.")
        executable = self.executable.expanduser().resolve()
        if not executable.is_file():
            raise CommandSecretBrokerError("Secret broker command was not found.")
        if self.timeout_seconds <= 0:
            raise CommandSecretBrokerError("Secret broker timeout must be positive.")

        try:
            result = self.runner(
                [str(executable), normalized_reference],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CommandSecretBrokerError(
                "Secret broker command failed without exposing secret output."
            ) from exc

        if result.returncode != 0:
            raise CommandSecretBrokerError(
                "Secret broker command returned a failure status."
            )
        value = result.stdout.rstrip("\r\n")
        if not value:
            raise CommandSecretBrokerError("Secret broker returned an empty value.")
        return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one governed, read-only CAP-001 Autotask validation."
    )
    parser.add_argument("--ticket-number", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--allowed-scope", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--username-reference", required=True)
    parser.add_argument("--secret-reference", required=True)
    parser.add_argument("--integration-code-reference", required=True)
    parser.add_argument("--secret-command", type=Path, required=True)
    parser.add_argument(
        "--live-read",
        action="store_true",
        help="Explicitly acknowledge that one live, read-only Autotask request may occur.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate configuration without resolving secrets or contacting Autotask.",
    )
    return parser


def validate_configuration(args: argparse.Namespace) -> None:
    required_text = {
        "ticket-number": args.ticket_number,
        "company-id": args.company_id,
        "scope": args.scope,
        "allowed-scope": args.allowed_scope,
        "username-reference": args.username_reference,
        "secret-reference": args.secret_reference,
        "integration-code-reference": args.integration_code_reference,
    }
    missing = [name for name, value in required_text.items() if not str(value).strip()]
    if missing:
        raise ValueError("Required values are blank: " + ", ".join(sorted(missing)))
    if args.scope.strip() != args.allowed_scope.strip():
        raise PermissionError("Requested scope does not match the authorized scope.")

    output = args.evidence_output.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Evidence output already exists; overwrite is denied.")

    command = args.secret_command.expanduser().resolve()
    if not command.is_file():
        raise FileNotFoundError("Secret broker command was not found.")


def run(args: argparse.Namespace) -> Path | None:
    validate_configuration(args)
    if args.check_only:
        return None
    if not args.live_read:
        raise PermissionError("Live read requires the explicit --live-read acknowledgement.")

    broker = CommandSecretBroker(executable=args.secret_command)
    credentials = AutotaskCredentialReferences(
        username=args.username_reference,
        secret=args.secret_reference,
        integration_code=args.integration_code_reference,
    )
    transport = build_autotask_ticket_transport(
        credentials=credentials,
        secrets=broker,
    )
    provider = AutotaskTicketProvider(transport=transport)
    validator = AutotaskLiveReadValidator(
        provider=provider,
        allowed_scope=args.allowed_scope,
    )
    validator.validate(
        LiveReadValidationRequest(
            ticket_number=args.ticket_number,
            company_id=args.company_id,
            scope_name=args.scope,
            live_read_acknowledged=True,
        ),
        output_path=args.evidence_output,
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
        print("APPROVED: Configuration validated; no secrets resolved and no network call made.")
    else:
        print("APPROVED: Read-only Autotask validation completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
