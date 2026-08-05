from __future__ import annotations

from pathlib import Path

import pytest

from jason_cap_001.secret_provider_readiness import (
    DeploymentReadinessError,
    evaluate_deployment_record,
    require_deployment_ready,
)


def write_record(path: Path, rows: list[str]) -> Path:
    path.write_text(
        "# Deployment Record\n\n"
        "| Field | Verified value | Status |\n"
        "|---|---|---|\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_reports_blocking_fields_deterministically(tmp_path: Path) -> None:
    record = write_record(
        tmp_path / "record.md",
        [
            "| Runtime type | UNVERIFIED | Blocking |",
            "| Canonical wrapper | /usr/local/bin/jason-secret | NOT IMPLEMENTED |",
            "| Selected provider | OpenBao | Verified |",
        ],
    )

    result = evaluate_deployment_record(record)

    assert result.ready is False
    assert result.blocking_fields == ("Runtime type", "Canonical wrapper")


def test_approved_record_passes(tmp_path: Path) -> None:
    record = write_record(
        tmp_path / "record.md",
        [
            "| Runtime type | system service | Verified |",
            "| Canonical wrapper | /usr/local/bin/jason-secret | Verified |",
            "| Audit device | enabled | Verified |",
        ],
    )

    result = require_deployment_ready(record)

    assert result.ready is True
    assert result.blocking_fields == ()


def test_missing_record_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(DeploymentReadinessError, match="was not found"):
        require_deployment_ready(tmp_path / "missing.md")


def test_error_names_exact_remediation_fields(tmp_path: Path) -> None:
    record = write_record(
        tmp_path / "record.md",
        ["| Authentication method | UNVERIFIED | Blocking |"],
    )

    with pytest.raises(DeploymentReadinessError) as captured:
        require_deployment_ready(record)

    message = str(captured.value)
    assert "Authentication method" in message
    assert str(record.resolve()) in message
