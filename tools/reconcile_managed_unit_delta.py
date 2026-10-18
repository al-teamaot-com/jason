#!/usr/bin/env python3
"""Plan a tightly bounded release-owned systemd unit removal during reconciliation.

No service actions are performed here. Root host reconciliation consumes only
the validated unit names. Only candidate-declared, installed, byte-identical
Jason units absent from the target release may be removed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

UNIT = re.compile(r"jason-[a-z0-9][a-z0-9-]*\.(?:service|timer|path)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
RELATIVE_SYSTEM_SOURCES = (
    "infrastructure/showcase/systemd",
    "infrastructure/openclaw-operations/systemd",
)
RELATIVE_USER_SOURCES = (
    "infrastructure/openclaw-operations/systemd/user",
    "infrastructure/showcase/systemd/user",
)
MAX_AUTO_REMOVALS = 8


class UnitDeltaError(ValueError):
    pass


def declared_units(release: Path, scope: str) -> set[str]:
    path = release / "config/production-desired-state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        raise UnitDeltaError("unsupported production desired-state schema")
    required = data.get(f"required_{scope}_units")
    allowed = data.get(f"allowed_{scope}_units")
    if not isinstance(required, list) or not isinstance(allowed, list):
        raise UnitDeltaError("production desired-state unit lists are missing")
    names = set()
    for value in required + allowed:
        if not isinstance(value, str) or UNIT.fullmatch(value) is None:
            raise UnitDeltaError("unsafe or invalid Jason unit in release manifest")
        names.add(value)
    return names


def candidate_unit_file(candidate: Path, unit: str, scope: str) -> Path:
    roots = RELATIVE_SYSTEM_SOURCES if scope == "system" else RELATIVE_USER_SOURCES
    matches = []
    for root in roots:
        path = candidate / root / unit
        if path.is_symlink():
            raise UnitDeltaError(f"candidate unit definition is a symlink: {unit}")
        if path.is_file():
            matches.append(path)
    if len(matches) != 1:
        raise UnitDeltaError(f"candidate-only unit must have exactly one immutable definition: {unit}")
    return matches[0]


def plan_unit_removals(
    candidate: Path,
    target: Path,
    installed_dir: Path,
    *,
    scope: str,
    enforce_owner: bool = False,
) -> list[str]:
    """Return validated unit names; never act on production or systemd."""
    if scope not in {"system", "user"}:
        raise UnitDeltaError("unsupported scope")
    delta = declared_units(candidate, scope) - declared_units(target, scope)
    if len(delta) > MAX_AUTO_REMOVALS:
        raise UnitDeltaError("too many candidate-only units for automatic removal")
    removable = []
    # Stop triggering timers/path units before dependent service units.
    for unit in sorted(delta, key=lambda name: (name.endswith(".service"), name)):
        installed = installed_dir / unit
        if installed.is_symlink():
            raise UnitDeltaError(f"installed unit is a symlink: {unit}")
        if not installed.exists():
            continue
        if not installed.is_file():
            raise UnitDeltaError(f"installed unit is not a regular file: {unit}")
        if enforce_owner and installed.stat().st_uid != (0 if scope == "system" else 1000):
            raise UnitDeltaError(f"unexpected owner of installed unit: {unit}")
        source = candidate_unit_file(candidate, unit, scope)
        if installed.read_bytes() != source.read_bytes():
            raise UnitDeltaError(f"installed unit differs from candidate release: {unit}")
        removable.append(unit)
    return removable


def pinned_release(path: Path, release_root: Path) -> Path:
    try:
        root = release_root.resolve(strict=True)
        actual = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise UnitDeltaError("release is not an exact immutable release-root child") from exc
    if actual.parent != root or not SHA.fullmatch(actual.name):
        raise UnitDeltaError("release is not an exact immutable release-root child")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path("/opt/jason/releases"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--installed-dir", type=Path, required=True)
    parser.add_argument("--scope", choices=("system", "user"), required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("root host reconciliation is required")
    expected_installed = (
        Path("/etc/systemd/system")
        if args.scope == "system" else Path("/home/al/.config/systemd/user")
    )
    if args.installed_dir != expected_installed or args.installed_dir.is_symlink():
        parser.error("installed systemd directory must be the canonical fixed location")
    candidate = pinned_release(args.candidate, args.release_root)
    target = pinned_release(args.target, args.release_root)
    for unit in plan_unit_removals(
        candidate, target, args.installed_dir,
        scope=args.scope, enforce_owner=True,
    ):
        print(unit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
