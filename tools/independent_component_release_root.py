#!/usr/bin/env python3
"""Pinned, root-only entrypoint for a separately approved component release.

Source-only worktrees MUST NOT execute production actions. The authorized
installer must place this entrypoint and its imported dependencies under the
exact immutable trusted root below, and provide protected policy, signing trust,
CI attestation, state staging, locks, and runtime health probes.

No production controls or services are changed by installing this source PR.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from tools.independent_component_release import (
    ComponentReleaseController, ComponentReleaseDenied,
    PRODUCTION_ROOT, trusted_file, _load_json, release_id,
)
from tools.independent_component_host_adapter import IndependentComponentHost

TRUSTED_ENTRYPOINT = Path(
    "/opt/jason/independent-component-release/trusted/tools/independent_component_release_root.py"
)
APPROVAL_OUTBOX = Path(
    "/var/lib/jason/openclaw/release-manager/independent-component-owner-approvals"
)


def _installed() -> None:
    if os.geteuid() != 0 or Path(__file__).resolve() != TRUSTED_ENTRYPOINT:
        raise ComponentReleaseDenied("COMPONENT_ROOT_ENTRYPOINT_NOT_INSTALLED")
    if not TRUSTED_ENTRYPOINT.is_file() or TRUSTED_ENTRYPOINT.is_symlink():
        raise ComponentReleaseDenied("COMPONENT_ROOT_ENTRYPOINT_UNTRUSTED")
    meta = TRUSTED_ENTRYPOINT.lstat()
    if meta.st_uid != 0 or meta.st_mode & 0o222:
        raise ComponentReleaseDenied("COMPONENT_ROOT_ENTRYPOINT_WRITABLE")


def _controller() -> ComponentReleaseController:
    host = IndependentComponentHost(production=True)
    return ComponentReleaseController(
        root=PRODUCTION_ROOT,
        host_transaction=host.host_transaction,
        freeze_transaction=host.freeze_transaction,
        verify_protected=host.protected,
        verify_source_and_ci=host.source_and_ci,
        verify_image=host.image,
        observe_component=host.observe,
        activate_component=host.activate,
        restore_component=host.restore,
        verify_component=host.verify_component,
        production=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--candidate-sha", required=True)
    sub.add_parser("recover-interrupted-rollback")
    args = parser.parse_args(argv)
    # Validate this BEFORE reading a production path or constructing a host
    # adapter. There is intentionally no --unsafe, --no-freeze, --test-root,
    # --override, or caller-provided signing key option.
    _installed()
    controller = _controller()
    if args.command == "recover-interrupted-rollback":
        print(json.dumps(controller.recover_interrupted_rollback(), sort_keys=True))
        return 0
    candidate = args.candidate_sha
    identifier = release_id(candidate)
    manifest = _load_json(trusted_file(
        PRODUCTION_ROOT / "releases" / candidate / "manifest.json",
        production=True,
    ))
    # The request outbox is owned by the already-authenticated MCP service.
    # It supplies ONLY signed proof, never trusted release scope/configuration.
    path = APPROVAL_OUTBOX / (identifier + ".json")
    data = _load_json(trusted_file(
        path, production=True, allowed_uid=1000, allow_owner_write=True,
        max_bytes=32768,
    ))
    if (
        data.get("release_id") != identifier
        or data.get("candidate_sha") != candidate
        or data.get("component_id") != manifest.get("component_id")
        or data.get("image_digest") != manifest.get("image_digest")
        or data.get("organization_id") != "aot"
        or not isinstance(data.get("signed_owner_proof"), dict)
    ):
        raise ComponentReleaseDenied("COMPONENT_ROOT_REQUEST_SCOPE_INVALID")
    result = controller.promote(manifest, data["signed_owner_proof"])
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ComponentReleaseDenied, PermissionError, OSError, ValueError) as exc:
        print("DENIED: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
