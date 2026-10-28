"""Read-only source contract for MCP routine RW release parity."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "infrastructure/jason-mcp/production-deploy.sh"
COMPOSE = ROOT / "infrastructure/jason-runtime/compose.yaml"

def test_mcp_release_shell_syntax():
    completed = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr

def test_runtime_and_mcp_must_share_explicit_rw_profiles():
    shell = SCRIPT.read_text()
    compose = COMPOSE.read_text()
    for profile in ("JASON_AOT_ROUTINE_RW_PROFILE",
                    "JASON_IT_GLUE_ROUTINE_RW_PROFILE",
                    "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE"):
        assert profile in shell and profile in compose
    assert "ROUTINE_RW_ARGS" in shell
    assert "add_routine_profile" in shell

def test_dedicated_approle_host_mounts_reach_both_services():
    shell = SCRIPT.read_text()
    compose = COMPOSE.read_text()
    for prefix in ("JASON_IT_GLUE_RW", "JASON_ENTRA_USER_CREATE",
                   "JASON_ENTRA_ONBOARDING_PASSWORD"):
        for part in ("ROLE_ID", "SECRET_ID"):
            name = prefix + "_OPENBAO_" + part + "_HOST_PATH"
            assert name in shell and name in compose
    assert "add_routine_mount_pair" in shell
    assert "invalid routine RW AppRole source" in shell

def test_unset_rw_profile_is_not_promoted_implicitly():
    shell = SCRIPT.read_text()
    assert "unrecognized routine RW profile" in shell
    assert "if [ -n" in shell
    assert "--set-env" in shell

RUNTIME_SCRIPT = ROOT / "infrastructure/jason-runtime/production-deploy.sh"

def test_native_runtime_release_shell_syntax():
    result = subprocess.run(["bash", "-n", str(RUNTIME_SCRIPT)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_native_runtime_release_matches_mcp_exact_rw_profiles_and_mounts():
    runtime = RUNTIME_SCRIPT.read_text()
    mcp = SCRIPT.read_text()
    for token in ("JASON_AOT_ROUTINE_RW_PROFILE",
                  "JASON_IT_GLUE_ROUTINE_RW_PROFILE",
                  "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE",
                  "JASON_IT_GLUE_RW_OPENBAO_ROLE_ID_HOST_PATH",
                  "JASON_ENTRA_USER_CREATE_OPENBAO_ROLE_ID_HOST_PATH",
                  "JASON_ENTRA_ONBOARDING_PASSWORD_OPENBAO_ROLE_ID_HOST_PATH"):
        assert token in runtime and token in mcp
    assert "ROUTINE_RW_ARGS" in runtime
    assert "unrecognized routine RW profile" in runtime
    assert "invalid routine RW AppRole source" in runtime
