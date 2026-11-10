"""Verify existing native deployment scripts enforce retired V4 source policy.

Only the validators embedded in the shell scripts are executed.  The shell
scripts themselves, Docker, release state, providers and production are NEVER
invoked by these tests.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "config/mobile-release-approval-policy.json"
RUNTIME = ROOT / "infrastructure/jason-runtime/production-deploy.sh"
MCP = ROOT / "infrastructure/jason-mcp/production-deploy.sh"


def embedded_python(script: Path, marker: str, terminator: str) -> str:
    body = script.read_text()
    selected = body.split(marker, 1)
    assert len(selected) == 2, f"required source-bound validator absent in {script}"
    fenced = selected[1].split("<<'" + terminator + "'\n", 1)
    assert len(fenced) == 2
    end = fenced[1].split("\n" + terminator + "\n", 1)
    assert len(end) == 2
    return end[0] + "\n"


def run_validator(script: Path, marker: str, terminator: str, argument: Path):
    return subprocess.run(
        [sys.executable, "-", str(argument)],
        input=embedded_python(script, marker, terminator),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=12, check=False, cwd=ROOT,
    )


def test_source_restores_exact_prior_owner_reviewed_contract():
    doc = json.loads(SOURCE.read_text())
    assert doc["schema_version"] == "2.0"
    assert doc["policy_mode"] == "owner_reviewed"
    assert doc["owner_identity_ids"] == ["person-al"]
    assert set(doc["allowed_risk_profiles"]) == {"normal", "production_control_core"}
    assert "admin_approver_binding" not in doc
    assert "regular_requester_binding" not in doc
    assert doc["high_impact_review"]["signed_teams_identity_required"] is True


def test_runtime_native_shell_validator_restores_existing_owner_reviewed_mode():
    run = run_validator(
        RUNTIME, 'SOURCE_RELEASE_APPROVAL_MODE="$(python3', 'PY2', SOURCE,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "owner_reviewed"


def test_mcp_native_shell_validator_does_not_activate_v4_admin_profile():
    run = run_validator(
        MCP, 'SOURCE_ADMIN_APPROVER_PROFILE="$(python3', 'PY_ADMIN_ROLE', ROOT,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == ""


@pytest.mark.parametrize("bad", [
    {"admin_approver_binding": {
        "microsoft_tenant_id":"f7054323-d52b-4863-8c2f-1898f0b6077c",
        "microsoft_object_id":"bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
    }},
    {"policy_mode":"admin_approver_separated"},
    {"admin_approver_binding":{
        "microsoft_tenant_id":"f7054323-d52b-4863-8c2f-1898f0b6077c",
        "microsoft_object_id":"INVALID",
    }},
    {"owner_identity_ids":["person-entra-bee80bdcffb04c50b453c09d4d411f5f"]},
    {"high_impact_review":{"owner_exact_sha_required":True}},
])
def test_native_runtime_rejects_invalid_or_restored_v4_fields_before_execution(tmp_path,bad):
    payload=json.loads(SOURCE.read_text())
    payload.update(bad)
    p=tmp_path/"tampered.json"
    p.write_text(json.dumps(payload))
    run=run_validator(
        RUNTIME,'SOURCE_RELEASE_APPROVAL_MODE="$(python3','PY2',p,
    )
    assert run.returncode != 0
    assert "DENIED" in run.stderr


def test_native_scripts_do_not_contain_unreviewed_environment_shortcuts():
    runtime=RUNTIME.read_text()
    mcp=MCP.read_text()
    assert "JASON_RELEASE_MOBILE_APPROVAL_MODE" in runtime
    assert "SOURCE_RELEASE_APPROVAL_MODE" in runtime
    assert "owner_reviewed" in runtime
    assert 'JASON_AOT_ADMIN_APPROVER_PROFILE' in mcp
    assert 'SOURCE_ADMIN_APPROVER_PROFILE' in mcp
    assert "rollback-current" in mcp
    # A second auth path may not bypass the reviewed immutable source.
    assert "reviewed exact source" in mcp
