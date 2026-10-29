"""Source-level contract for the independently scoped Autotask-only Stage B."""
from pathlib import Path
import subprocess

from orchestrator.provider_read_authority import (
    AOT_ROUTINE_AUTOTASK_WRITE_CAPABILITIES,
    AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS,
)
from jason_runtime.aot_routine_write_authority import (
    AOT_ROUTINE_WRITE_PROFILE,
    AOT_ROUTINE_WRITE_PROFILE_ENV,
    configured_aot_routine_autotask_write,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = (
    ("infrastructure/jason-runtime/production-deploy.sh", "jason-runtime:rollback-current"),
    ("infrastructure/jason-mcp/production-deploy.sh", "jason-mcp:rollback-current"),
)
EXPECTED = {
    "service.ticket.create": "autotask_ticket_create",
    "service.ticket.update": "autotask_ticket_update",
    "service.ticket.note.create": "autotask_internal_note",
}


def test_exact_three_existing_autotask_capabilities_not_new_credential_scopes():
    assert AOT_ROUTINE_WRITE_PROFILE_ENV == "JASON_AOT_ROUTINE_RW_PROFILE"
    assert AOT_ROUTINE_WRITE_PROFILE == "autotask-ticket-v1"
    assert AOT_ROUTINE_AUTOTASK_WRITE_CAPABILITIES == frozenset(EXPECTED)
    assert AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS == EXPECTED


def test_off_by_default_and_only_exact_profile_opt_in(monkeypatch):
    monkeypatch.delenv(AOT_ROUTINE_WRITE_PROFILE_ENV, raising=False)
    assert not configured_aot_routine_autotask_write()
    for invalid in ("true", "1", "documentation.configuration.update", "cloud-user-v1"):
        monkeypatch.setenv(AOT_ROUTINE_WRITE_PROFILE_ENV, invalid)
        assert not configured_aot_routine_autotask_write()
    monkeypatch.setenv(AOT_ROUTINE_WRITE_PROFILE_ENV, AOT_ROUTINE_WRITE_PROFILE)
    assert configured_aot_routine_autotask_write()


def test_development_compose_has_only_new_autotask_flag_defaulting_off():
    compose = (ROOT / "infrastructure/jason-runtime/compose.yaml").read_text()
    assert f"{AOT_ROUTINE_WRITE_PROFILE_ENV}: ${{JASON_AOT_ROUTINE_RW_PROFILE:-}}" in compose
    # Stage B1 does not introduce IT Glue or Entra write flags or mounts.
    assert "JASON_IT_GLUE_ROUTINE_RW_PROFILE" not in compose
    assert "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE" not in compose
    assert "it-glue-write/" not in compose
    assert "microsoft-graph-user-create/" not in compose


def test_both_native_deployers_fail_closed_and_force_rollback_profile_off():
    for relative_path, rollback_image in SCRIPTS:
        path = ROOT / relative_path
        script = path.read_text()
        assert script.count("--set-env \"JASON_AOT_ROUTINE_RW_PROFILE=$AOT_ROUTINE_RW_PROFILE\"") == 1
        assert '""|autotask-ticket-v1)' in script
        assert 'echo "DENIED: unknown AOT routine Autotask ticket profile"' in script
        assert f'if [ "$IMAGE" = "{rollback_image}" ]; then' in script
        assert 'AOT_ROUTINE_RW_PROFILE=""' in script
        assert "JASON_IT_GLUE_ROUTINE_RW_PROFILE" not in script
        assert "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE" not in script
        subprocess.run(["bash", "-n", str(path)], check=True)
