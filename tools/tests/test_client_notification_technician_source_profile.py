"""Source-profile / rollback fail-closed contract for human client notifications."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from release_manager_host_runner import (
    MUTATION_ENV_OVERRIDES,
    ReleaseManagerError,
    declared_aot_client_notification_tech_profile,
    native_deploy_contract_digest,
)


def _write(tmp_path, data):
    path = tmp_path / "config" / "aot-client-notification-technician-profile.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_source_bound_profile_requires_specific_approved_value(tmp_path):
    assert declared_aot_client_notification_tech_profile(tmp_path) == ""
    path = _write(tmp_path, {
        "schema_version": "1.0",
        "profile": "off",
    })
    assert declared_aot_client_notification_tech_profile(tmp_path) == ""
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "profile": "approved-workflow-technician-v1",
    }))
    assert declared_aot_client_notification_tech_profile(tmp_path) == (
        "approved-workflow-technician-v1"
    )


@pytest.mark.parametrize("doc", [
    {"schema_version": "2.0", "profile": "approved-workflow-technician-v1"},
    {"schema_version": "1.0", "profile": "anything"},
    {"schema_version": "1.0", "profile": ""},
    {"schema_version": "1.0", "profile": "approved-workflow-technician-v1",
     "suppress_approval": True},
    [],
])
def test_unknown_profile_version_and_unreviewed_extras_rejected(tmp_path, doc):
    _write(tmp_path, doc)
    with pytest.raises(ReleaseManagerError):
        declared_aot_client_notification_tech_profile(tmp_path)


def test_profile_symlink_and_invalid_json_rejected(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    foreign = tmp_path / "outside.json"
    foreign.write_text('{"schema_version":"1.0","profile":"off"}')
    path = config / "aot-client-notification-technician-profile.json"
    path.symlink_to(foreign)
    with pytest.raises(ReleaseManagerError, match="symlink"):
        declared_aot_client_notification_tech_profile(tmp_path)
    path.unlink()
    path.write_text("not json")
    with pytest.raises(ReleaseManagerError):
        declared_aot_client_notification_tech_profile(tmp_path)


def test_preproduction_and_rollback_cannot_inherit_source_active_authority():
    assert MUTATION_ENV_OVERRIDES["JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE"] == ""
    old = {"JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE": ""}
    active = {"JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE": "approved-workflow-technician-v1"}
    assert native_deploy_contract_digest(old) != native_deploy_contract_digest(active)


def test_native_deploy_and_compose_align_on_exact_source_activation():
    repo = Path(__file__).resolve().parents[2]
    for service in ("jason-runtime", "jason-mcp"):
        script = (repo / "infrastructure" / service / "production-deploy.sh").read_text()
        assert "declared_aot_client_notification_tech_profile" in script
        assert (
            '--set-env "JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE=$CLIENT_NOTIFICATION_TECH_PROFILE"'
            in script
        )
        assert f'if [ "$IMAGE" = "{service}:rollback-current" ]; then\n  CLIENT_NOTIFICATION_TECH_PROFILE=""' in script
        assert "client-notification technician authority differs from immutable source" in script
    compose = (repo / "infrastructure/jason-runtime/compose.yaml").read_text()
    assert "JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE" in compose
    assert (repo / "config/aot-client-notification-technician-profile.json").is_file()
