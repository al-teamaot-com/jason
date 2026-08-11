#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "docs/index.md",
    "docs/control/CURRENT.md",
    "docs/control/DOCUMENTATION-REGISTER.md",
    "docs/control/HOW-TO-DOCUMENT-JASON.md",
    "docs/control/HANDOFF-TEMPLATE.md",
    "docs/control/DOCUMENT-TEMPLATE.md",
    "docs/standards/J-404-Documentation-Governance-and-Continuity.md",
)

LEGACY_ROOTS = (
    "01-Foundation/",
    "01-Governance/",
    "02-Architecture/",
    "02-Canonical-Models/",
    "03-Components/",
    "04-Standards/",
    "05-ADR/",
    "06-Roadmaps/",
    "07-Operations/",
    "07-Roadmap/",
    "08-Session-Records/",
    "09-Architecture-Journal/",
    "10-Milestones/",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def read(path: str) -> str:
    file_path = ROOT / path
    if not file_path.is_file():
        fail(f"Required documentation-control file is missing: {path}")
    return file_path.read_text(encoding="utf-8")


def main() -> int:
    for path in REQUIRED_FILES:
        read(path)

    index = read("docs/index.md")
    for path in REQUIRED_FILES[1:]:
        relative = path.removeprefix("docs/")
        if relative not in index:
            fail(f"docs/index.md does not link to required control record: {relative}")

    repository_readme = read("README.md")
    if "docs/index.md" not in repository_readme:
        fail("README.md must direct readers to docs/index.md")

    contributing = read("CONTRIBUTING.md")
    if "docs/control/HOW-TO-DOCUMENT-JASON.md" not in contributing:
        fail("CONTRIBUTING.md must require the Jason documentation authoring guide")

    register = read("docs/control/DOCUMENTATION-REGISTER.md")
    for root in LEGACY_ROOTS:
        if root not in register:
            fail(f"Documentation Register is missing legacy-root migration coverage: {root}")

    how_to = read("docs/control/HOW-TO-DOCUMENT-JASON.md")
    required_practices = (
        "Search before creating",
        "Separate intended state, actual state, and proof",
        "System Registry documentation rules",
        "Session and proof records",
        "Current-work record",
        "Security rules",
        "Future-session startup procedure",
    )
    for heading in required_practices:
        if heading not in how_to:
            fail(f"Documentation authoring guide is missing required practice: {heading}")

    standard = read("docs/standards/J-404-Documentation-Governance-and-Continuity.md")
    for phrase in (
        "Single documentation control plane",
        "One fact, one authoritative owner",
        "Current-work continuity",
        "Documentation migration",
        "Definition of documentation complete",
    ):
        if phrase not in standard:
            fail(f"J-404 is missing required governance section: {phrase}")

    assembly = read("tools/assemble_docs.py")
    for source in ("docs/control", "docs/standards"):
        if source not in assembly:
            fail(f"Documentation assembly does not publish control-plane source: {source}")

    mkdocs = read("mkdocs.yml")
    for path in (
        "control/CURRENT.md",
        "control/DOCUMENTATION-REGISTER.md",
        "control/HOW-TO-DOCUMENT-JASON.md",
        "standards/J-404-Documentation-Governance-and-Continuity.md",
    ):
        if path not in mkdocs:
            fail(f"MkDocs navigation is missing documentation-control record: {path}")

    print("Documentation control-plane validation: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
