from __future__ import annotations

from pathlib import Path

import pytest

from tools.documentation_readiness import (
    DocumentationReadinessError,
    DocumentationReadinessGate,
)


def write_record(
    root: Path,
    *,
    version: str = "0.2.0",
    release_name: str = "Governed Release",
    status: str = "Complete",
    filename: str = "M-003-Governed-Release.md",
    navigate: bool = True,
) -> Path:
    milestone_root = root / "10-Milestones"
    milestone_root.mkdir(parents=True, exist_ok=True)
    record = milestone_root / filename
    record.write_text(
        "\n".join(
            (
                "# M-003 — Governed Release",
                "",
                f"**Version:** {version}",
                f"**Release Name:** {release_name}",
                f"**Status:** {status}",
                "**Owner:** Jason Architecture Authority",
                "",
            )
        ),
        encoding="utf-8",
    )
    navigation_entry = (
        f"      - Governed Release: 10-Milestones/{filename}\n"
        if navigate
        else ""
    )
    (root / "mkdocs.yml").write_text(
        "nav:\n  - Milestones:\n" + navigation_entry,
        encoding="utf-8",
    )
    return record


def test_approved_release_record_passes(tmp_path: Path) -> None:
    record = write_record(tmp_path)

    result = DocumentationReadinessGate(tmp_path).verify(
        "v0.2.0",
        release_name="Governed Release",
    )

    assert result.version == "v0.2.0"
    assert result.status == "Complete"
    assert result.record_path == record.relative_to(tmp_path)


def test_missing_release_record_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "10-Milestones").mkdir()
    (tmp_path / "mkdocs.yml").write_text("nav: []\n", encoding="utf-8")

    with pytest.raises(DocumentationReadinessError, match="No approved"):
        DocumentationReadinessGate(tmp_path).verify(
            "v0.2.0",
            release_name="Governed Release",
        )


def test_incomplete_release_record_fails_closed(tmp_path: Path) -> None:
    write_record(tmp_path, status="Draft")

    with pytest.raises(DocumentationReadinessError, match="Complete or Approved"):
        DocumentationReadinessGate(tmp_path).verify(
            "v0.2.0",
            release_name="Governed Release",
        )


def test_release_record_must_be_in_navigation(tmp_path: Path) -> None:
    write_record(tmp_path, navigate=False)

    with pytest.raises(DocumentationReadinessError, match="navigation"):
        DocumentationReadinessGate(tmp_path).verify(
            "v0.2.0",
            release_name="Governed Release",
        )


def test_release_name_must_match(tmp_path: Path) -> None:
    write_record(tmp_path)

    with pytest.raises(DocumentationReadinessError, match="No approved"):
        DocumentationReadinessGate(tmp_path).verify(
            "v0.2.0",
            release_name="Different Release",
        )
