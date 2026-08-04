#!/usr/bin/env python3

from __future__ import annotations

import shutil
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPOSITORY_ROOT / ".build" / "docs"

CANONICAL_DIRECTORIES = (
    "01-Foundation",
    "01-Governance",
    "02-Architecture",
    "02-Canonical-Models",
    "03-Components",
    "04-Standards",
    "05-ADR",
    "06-Roadmaps",
    "07-Operations",
    "07-Roadmap",
    "08-Session-Records",
    "09-Architecture-Journal",
    "10-Milestones",
)

PUBLISHING_DIRECTORIES = (
    "docs/architecture",
    "docs/governance",
)


class AssemblyError(Exception):
    pass


def copy_directory(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise AssemblyError(f"Required source directory is missing: {source}")

    shutil.copytree(source, destination)


def main() -> int:
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)

    BUILD_ROOT.mkdir(parents=True, exist_ok=False)

    for directory_name in CANONICAL_DIRECTORIES:
        source = REPOSITORY_ROOT / directory_name
        destination = BUILD_ROOT / directory_name
        copy_directory(source, destination)

    for directory_name in PUBLISHING_DIRECTORIES:
        source = REPOSITORY_ROOT / directory_name
        destination = BUILD_ROOT / directory_name
        copy_directory(source, destination)

    index_source = REPOSITORY_ROOT / "docs" / "index.md"
    index_destination = BUILD_ROOT / "index.md"

    if not index_source.is_file():
        raise AssemblyError(
            f"Required documentation entry point is missing: {index_source}"
        )

    shutil.copy2(index_source, index_destination)

    print(f"Documentation assembled at: {BUILD_ROOT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssemblyError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
