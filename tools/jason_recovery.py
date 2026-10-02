from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from tools.full_recovery_package import (
    RecoveryPackageError,
    decrypt_recovery_package,
    inspect_recovery_package,
    verify_recovery_package_signature,
)
from tools.full_recovery_restore import (
    apply_recovery_restore_plan,
    plan_recovery_restore,
)


def _load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_signer_public(path: str | Path) -> Ed25519PublicKey:
    key = load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise RecoveryPackageError("signer public key is not Ed25519")
    return key


def _load_recovery_private(path: str | Path) -> X25519PrivateKey:
    key = load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, X25519PrivateKey):
        raise RecoveryPackageError("recovery private key is not X25519")
    return key


def command_inspect(args: argparse.Namespace) -> int:
    package = _load_json(args.package)
    summary = inspect_recovery_package(package)
    print(json.dumps(summary.__dict__ if hasattr(summary, "__dict__") else {
        "format": summary.format,
        "format_version": summary.format_version,
        "created_at": summary.created_at,
        "source_deployment_identity_sha256": summary.source_deployment_identity_sha256,
        "recipient_key_id": summary.recipient_key_id,
        "signer_key_id": summary.signer_key_id,
        "payload_ciphertext_sha256": summary.payload_ciphertext_sha256,
    }, indent=2, sort_keys=True))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    package = _load_json(args.package)
    signer_public = _load_signer_public(args.signer_public_key)
    verify_recovery_package_signature(package, signer_public_key=signer_public)

    result = {
        "status": "valid",
        "signature": "valid",
        "decryptability": "not_checked",
        "member_count": None,
    }
    if args.recovery_private_key:
        recovery_private = _load_recovery_private(args.recovery_private_key)
        members = decrypt_recovery_package(
            package,
            recipient_private_key=recovery_private,
            signer_public_key=signer_public,
        )
        result["decryptability"] = "valid"
        result["member_count"] = len(members)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0




def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _restore_inputs(args: argparse.Namespace):
    package = _load_json(args.package)
    signer_public = _load_signer_public(args.signer_public_key)
    recovery_private = _load_recovery_private(args.recovery_private_key)
    members = decrypt_recovery_package(
        package,
        recipient_private_key=recovery_private,
        signer_public_key=signer_public,
    )
    inventory = _load_json(args.state_inventory)
    payload_schema = _load_json(args.payload_manifest_schema)
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=inventory,
        payload_manifest_schema=payload_schema,
        target_root=args.target_root,
        expected_source_deployment_identity_sha256=args.expected_source_deployment_id,
    )
    return members, plan


def command_plan_restore(args: argparse.Namespace) -> int:
    _, plan = _restore_inputs(args)
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    return 0 if plan.status == "ready_for_restore" else 3


def command_restore_to_root(args: argparse.Namespace) -> int:
    members, plan = _restore_inputs(args)
    if plan.status != "ready_for_restore":
        print(json.dumps(asdict(plan), indent=2, sort_keys=True))
        return 3
    result = apply_recovery_restore_plan(
        plan=plan,
        decrypted_members=members,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jason recovery package inspection and validation")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="inspect non-secret package metadata")
    inspect_parser.add_argument("package")
    inspect_parser.set_defaults(func=command_inspect)

    validate_parser = sub.add_parser("validate", help="verify package authenticity/integrity")
    validate_parser.add_argument("package")
    validate_parser.add_argument("--signer-public-key", required=True)
    validate_parser.add_argument("--recovery-private-key")
    validate_parser.set_defaults(func=command_validate)

    repo = _repo_root()
    for name, handler, help_text in (
        ("plan-restore", command_plan_restore, "validate and plan a non-production restore"),
        ("restore-to-root", command_restore_to_root, "apply a validated restore to a non-live target root"),
    ):
        restore_parser = sub.add_parser(name, help=help_text)
        restore_parser.add_argument("package")
        restore_parser.add_argument("--signer-public-key", required=True)
        restore_parser.add_argument("--recovery-private-key", required=True)
        restore_parser.add_argument("--target-root", required=True)
        restore_parser.add_argument(
            "--expected-source-deployment-id",
            required=True,
        )
        restore_parser.add_argument(
            "--state-inventory",
            default=str(repo / "config/recovery-state-inventory.v1.json"),
        )
        restore_parser.add_argument(
            "--payload-manifest-schema",
            default=str(repo / "config/schemas/full-recovery-payload-manifest.schema.json"),
        )
        restore_parser.set_defaults(func=handler)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (RecoveryPackageError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
