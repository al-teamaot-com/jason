from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from tools.release_evidence import (
    ReleaseEvidenceError,
    ReleaseEvidenceWriter,
)


COMMIT = "a" * 40
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def package(tmp_path: Path) -> Path:
    root = tmp_path / "v0.1.4"
    root.mkdir()
    (root / "artifact.txt").write_text("artifact\n", encoding="utf-8")
    (root / "SHA256SUMS.txt").write_text("", encoding="utf-8")
    return root


def test_writes_json_markdown_and_verified_checksums(tmp_path: Path) -> None:
    root = package(tmp_path)
    result = ReleaseEvidenceWriter(
        tmp_path,
        clock=lambda: NOW,
    ).write(
        version="v0.1.4",
        release_name="Release Governance Hardening",
        commit=COMMIT,
        package_directory=root,
        documentation_path=Path("10-Milestones/M-003.md"),
        validation_step_ids=("tests", "docs"),
        restored_commit=COMMIT,
    )

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["overall_status"] == "approved"
    assert report["commit"] == COMMIT
    assert report["validation"]["steps"] == ["tests", "docs"]
    assert "Overall status:** APPROVED" in result.summary_path.read_text(
        encoding="utf-8"
    )

    checksum_names = {
        line.split("  ", maxsplit=1)[1]
        for line in result.checksums_path.read_text(
            encoding="utf-8"
        ).splitlines()
    }
    assert checksum_names == {
        "artifact.txt",
        "release-report.json",
        "release-summary.md",
    }


def test_rejects_commit_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ReleaseEvidenceError, match="does not match"):
        ReleaseEvidenceWriter(tmp_path).write(
            version="v0.1.4",
            release_name="Release Governance Hardening",
            commit=COMMIT,
            package_directory=package(tmp_path),
            documentation_path=Path("10-Milestones/M-003.md"),
            validation_step_ids=("tests",),
            restored_commit="b" * 40,
        )


def test_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    root = package(tmp_path)
    (root / "release-report.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ReleaseEvidenceError, match="already exists"):
        ReleaseEvidenceWriter(tmp_path).write(
            version="v0.1.4",
            release_name="Release Governance Hardening",
            commit=COMMIT,
            package_directory=root,
            documentation_path=Path("10-Milestones/M-003.md"),
            validation_step_ids=("tests",),
            restored_commit=COMMIT,
        )
