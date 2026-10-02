from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import stat
from typing import Callable

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    load_candidate_host_identity,
)
from bootstrap.clean_install import (
    HostObservation,
    observe_host,
    validate_supported_host,
)


@dataclass(frozen=True, slots=True)
class CandidateHostPreflightResult:
    schema_version: str
    status: str
    instance_id: str
    host: HostObservation
    blockers: tuple[str, ...]
    clean_host: bool


def _identity_permissions_ok(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    mode = stat.S_IMODE(path.stat().st_mode)
    return (mode & 0o022) == 0


def _prior_jason_markers(root: Path) -> tuple[str, ...]:
    markers = (
        "opt/jason/current",
        "var/lib/jason/deployment-manifest.json",
        "var/lib/jason/deployment-bootstrap.json",
        "var/lib/jason/candidate-ready.json",
    )
    found = [item for item in markers if (root / item).exists() or (root / item).is_symlink()]
    systemd = root / "etc/systemd/system"
    if systemd.is_dir():
        found.extend(
            str(path.relative_to(root))
            for path in sorted(systemd.glob("jason-*.service"))
        )
        found.extend(
            str(path.relative_to(root))
            for path in sorted(systemd.glob("jason-*.timer"))
        )
    return tuple(sorted(set(found)))


def preflight_candidate_host(
    *,
    root: str | Path,
    identity_path: str | Path,
    host: HostObservation | None = None,
    effective_uid: int | None = None,
) -> CandidateHostPreflightResult:
    candidate_root = Path(root)
    if not candidate_root.is_absolute():
        raise ValueError("candidate host root must be absolute")

    identity_file = Path(identity_path)
    identity: CandidateHostIdentity = load_candidate_host_identity(identity_file)
    blockers: list[str] = []

    if not _identity_permissions_ok(identity_file):
        blockers.append("candidate_identity_permissions_invalid")

    uid = os.geteuid() if effective_uid is None else int(effective_uid)
    if uid != 0:
        blockers.append("root_privileges_required")

    observation = host or observe_host()
    try:
        validate_supported_host(
            observation,
            require_container_runtime=True,
        )
    except ValueError as exc:
        blockers.append("host_prerequisite:" + str(exc))

    existing = _prior_jason_markers(candidate_root)
    blockers.extend("prior_jason_state:" + item for item in existing)

    return CandidateHostPreflightResult(
        schema_version="1.0",
        status="ready_for_host_install" if not blockers else "blocked",
        instance_id=identity.instance_id,
        host=observation,
        blockers=tuple(blockers),
        clean_host=not existing,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Read-only preflight for a blank Jason candidate host"
    )
    parser.add_argument("--root", default="/")
    parser.add_argument(
        "--candidate-host-identity",
        required=True,
    )
    args = parser.parse_args()

    result = preflight_candidate_host(
        root=args.root,
        identity_path=args.candidate_host_identity,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0 if result.status == "ready_for_host_install" else 3


if __name__ == "__main__":
    raise SystemExit(main())
