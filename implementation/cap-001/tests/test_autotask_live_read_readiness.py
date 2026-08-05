from __future__ import annotations

from pathlib import Path

import pytest

from jason_cap_001.autotask_live_read_command import build_parser, run
from jason_cap_001.secret_provider_readiness import DeploymentReadinessError


def test_live_read_is_denied_before_secret_resolution_when_record_is_blocked(
    tmp_path: Path,
) -> None:
    command = tmp_path / "secret-command"
    command.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    record = tmp_path / "deployment.md"
    record.write_text(
        "# Deployment\n\n"
        "| Field | Verified value | Status |\n"
        "|---|---|---|\n"
        "| Canonical wrapper | /usr/local/bin/jason-secret | NOT IMPLEMENTED |\n",
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "--ticket-number", "T20260805.0001",
            "--company-id", "1001",
            "--scope", "aot-validation",
            "--allowed-scope", "aot-validation",
            "--evidence-output", str(tmp_path / "evidence.json"),
            "--username-reference", "autotask.readonly.username",
            "--secret-reference", "autotask.readonly.secret",
            "--integration-code-reference", "autotask.readonly.integration_code",
            "--secret-command", str(command),
            "--deployment-record", str(record),
            "--live-read",
        ]
    )

    with pytest.raises(DeploymentReadinessError, match="Canonical wrapper"):
        run(args)

    assert not (tmp_path / "evidence.json").exists()
