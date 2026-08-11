#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "docs/index.md",
    "docs/control/CURRENT.md",
    "docs/control/DOCUMENTATION-REGISTER.md",
    "docs/control/DOCUMENTATION-MIGRATION-ISSUES.md",
    "docs/control/HOW-TO-DOCUMENT-JASON.md",
    "docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md",
    "docs/control/HANDOFF-TEMPLATE.md",
    "docs/control/DOCUMENT-TEMPLATE.md",
    "docs/standards/J-404-Documentation-Governance-and-Continuity.md",
    "docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md",
    "docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md",
    "docs/decisions/ADR-008-Documentation-Control-Plane-Consolidation.md",
    "docs/roadmaps/Jason-Roadmap-Status.json",
    "docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md",
    "docs/engineering/README.md",
)

LEGACY_ROOTS = (
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
    "architecture",
)

REQUIRED_DOC_DIRECTORIES = (
    "docs/control",
    "docs/foundation",
    "docs/governance",
    "docs/architecture",
    "docs/engineering",
    "docs/models",
    "docs/components",
    "docs/standards",
    "docs/decisions",
    "docs/roadmaps",
    "docs/operations",
    "docs/sessions",
    "docs/journal",
    "docs/milestones",
    "docs/archive",
)

IMPLEMENTATION_README_ROOTS = (
    "implementation",
    "infrastructure",
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

    for path in REQUIRED_DOC_DIRECTORIES:
        if not (ROOT / path).is_dir():
            fail(f"Required consolidated documentation directory is missing: {path}")

    for root in LEGACY_ROOTS:
        if (ROOT / root).exists():
            fail(
                "Legacy human-documentation root must not be recreated after consolidation: "
                + root
            )

    if (ROOT / "TODO.md").exists():
        fail("Governed backlog must remain under docs/roadmaps, not repository-root TODO.md")

    if (ROOT / "docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md").exists():
        fail(
            "Historical Platform Integrity Article VII must remain archived rather than "
            "reappearing as current governance authority"
        )

    index = read("docs/index.md")
    for path in REQUIRED_FILES[1:9]:
        relative = path.removeprefix("docs/")
        if relative not in index:
            fail(f"docs/index.md does not link to required control record: {relative}")
    for path in ("engineering/", "roadmaps/"):
        if path not in index:
            fail(f"docs/index.md does not expose consolidated documentation area: {path}")

    repository_readme = read("README.md")
    if "docs/index.md" not in repository_readme:
        fail("README.md must direct readers to docs/index.md")

    contributing = read("CONTRIBUTING.md")
    if "docs/control/HOW-TO-DOCUMENT-JASON.md" not in contributing:
        fail("CONTRIBUTING.md must require the Jason documentation authoring guide")

    register = read("docs/control/DOCUMENTATION-REGISTER.md")
    for root in LEGACY_ROOTS:
        if f"`{root}/`" not in register and f"`{root}`" not in register:
            fail(f"Documentation Register is missing migration history for: {root}")

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
        "docs/engineering/",
    ):
        if phrase not in standard:
            fail(f"J-404 is missing required governance section or path: {phrase}")

    platform_integrity = read(
        "docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md"
    )
    for phrase in (
        "Prohibited bypasses",
        "Central orchestration",
        "Policy and business authority separation",
        "Integrate before innovate",
        "Exception governance",
        "Production-readiness enforcement",
        "ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md",
    ):
        if phrase not in platform_integrity:
            fail(f"J-405 is missing required platform-integrity control: {phrase}")

    historical_platform_integrity = read(
        "docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md"
    )
    if "Historical / Superseded as governing authority" not in historical_platform_integrity:
        fail("Archived Platform Integrity record must be explicitly historical/superseded")
    if "# Article VII - Platform Integrity" not in historical_platform_integrity:
        fail("Archived Platform Integrity record must preserve the historical source text")

    migration_issues = read("docs/control/DOCUMENTATION-MIGRATION-ISSUES.md")
    if "MIG-DOC-003" not in migration_issues or "Resolved through deliberate governance disposition" not in migration_issues:
        fail("MIG-DOC-003 Platform Integrity conflict must remain recorded as resolved")

    adr008 = read("docs/decisions/ADR-008-Documentation-Control-Plane-Consolidation.md")
    if "**Supersedes:** ADR-002" not in adr008:
        fail("ADR-008 must explicitly supersede ADR-002")

    adr002 = read("docs/decisions/ADR-002-Canonical-Documentation-Layout.md")
    if "**Status:** Superseded by ADR-008" not in adr002:
        fail("ADR-002 must be explicitly marked superseded by ADR-008")

    if not (ROOT / "docs/decisions/ADR-004-Datto-RMM-Managed-Device-Authority.md").is_file():
        fail("Canonical ADR-004 Datto authority record is missing")
    if not (ROOT / "docs/decisions/ADR-007-Teams-Proactive-Messaging.md").is_file():
        fail("Corrected ADR-007 Teams proactive messaging record is missing")

    implementation_index = read("docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md")
    for root in IMPLEMENTATION_README_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for readme in sorted(base.rglob("README.md")):
            relative = readme.relative_to(ROOT).as_posix()
            if relative not in implementation_index:
                fail(
                    "Material implementation-local README is not represented in "
                    f"the implementation documentation index: {relative}"
                )

    mkdocs = read("mkdocs.yml")
    if "docs_dir: docs" not in mkdocs:
        fail("MkDocs must publish directly from the canonical docs tree")
    if ".build/docs" in mkdocs:
        fail("MkDocs must not depend on the retired mixed-source documentation assembly tree")

    for path in (
        "control/CURRENT.md",
        "control/DOCUMENTATION-REGISTER.md",
        "control/HOW-TO-DOCUMENT-JASON.md",
        "control/IMPLEMENTATION-DOCUMENTATION-INDEX.md",
        "standards/J-404-Documentation-Governance-and-Continuity.md",
        "standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md",
        "decisions/ADR-008-Documentation-Control-Plane-Consolidation.md",
        "engineering/README.md",
        "roadmaps/Project-Jason-TODO-and-Future-Ideas.md",
    ):
        if path not in mkdocs:
            fail(f"MkDocs navigation is missing documentation-control record: {path}")

    catch_me_up = read("tools/catch_me_up.py")
    required_current_signals = (
        "docs/control/CURRENT.md",
        "docs/control/HOW-TO-DOCUMENT-JASON.md",
        "docs/roadmaps/Jason-Roadmap-Status.json",
        "docs/operations/System-Registry-Current-Operational-State.md",
        "collect_session_records",
    )
    for signal in required_current_signals:
        if signal not in catch_me_up:
            fail(f"CatchMeUp is missing consolidated continuity signal: {signal}")

    print("Documentation control-plane validation: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
