"""Source-only PMv4 runbook component lifecycle acceptance."""
from __future__ import annotations
import os
from pathlib import Path

import pytest

from tools import pmv4_runbook_lifecycle_acceptance as lab


def test_separate_local_processes_share_existing_json_registry():
    result = lab.acceptance("local")
    assert result["status"] == "accepted"
    assert result["distinct_lifecycle_processes"] == 6
    assert result["final_generation"] == 5
    assert result["provider_access"] is False
    assert result["owner_authorization_issued"] is False
    assert result["production_mounts"] is False
    assert result["production_deployed"] is False


def test_docker_command_is_hard_isolated_and_does_not_mount_production(tmp_path):
    command = lab.command_for_phase("stage", tmp_path, "local")
    assert "--child" in command
    if os.geteuid() == 0:
        with pytest.raises(ValueError, match="non-root"):
            lab.command_for_phase("stage", tmp_path, "docker")
        return
    args = lab.command_for_phase("stage", tmp_path, "docker")
    assert "--network" in args and args[args.index("--network") + 1] == "none"
    assert "--read-only" in args and "--cap-drop" in args
    assert args[args.index("--user") + 1] == f"{os.geteuid()}:{os.getegid()}"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert not any(":/var/lib/jason/openclaw" in x for x in args)
    assert not any("provider-secret" in x for x in args)
    assert "docker" == args[0]
    assert "--child" in args and "stage" in args


def test_malformed_playbook_is_not_accepted(tmp_path):
    from autonomous_remediation.playbook_document import (
        PlaybookValidationError, validate_playbook_document,
    )
    payload = lab.sample()
    payload["steps"][0]["powershell"] = "not permitted"
    with pytest.raises(PlaybookValidationError, match="INLINE_EXECUTION_FORBIDDEN"):
        validate_playbook_document(payload)
