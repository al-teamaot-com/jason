from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectors.core.contracts import ConnectorAuthorizationError
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)
from jason_runtime.routine_rw_registration import (
    ENTRA_USER_CREATE, ENTRA_PROFILE, ENTRA_PROFILE_ENV, IT_GLUE_NOTES,
    IT_GLUE_PROFILE, IT_GLUE_PROFILE_ENV, register_routine_rw_foundation,
)
from jason_runtime.routine_rw_runtime import bootstrap_present, configured_credential_paths


def registration():
    caps = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    status = register_routine_rw_foundation(
        capabilities=caps, providers=providers, now=datetime.now(timezone.utc),
        bootstrap_present=bootstrap_present,
    )
    return caps, providers, status


def test_default_off_neither_active(monkeypatch):
    monkeypatch.delenv(IT_GLUE_PROFILE_ENV, raising=False)
    monkeypatch.delenv(ENTRA_PROFILE_ENV, raising=False)
    caps, providers, status = registration()
    assert not status.enabled_capabilities
    assert not status.blocked_capabilities
    assert all(x.lifecycle_status == CapabilityLifecycle.BUILDING
               for x in caps.list_all())


def test_profile_on_without_write_secret_remains_inactive(monkeypatch, tmp_path):
    monkeypatch.setenv(IT_GLUE_PROFILE_ENV, IT_GLUE_PROFILE)
    monkeypatch.setenv(ENTRA_PROFILE_ENV, ENTRA_PROFILE)
    for key in ("IT_GLUE_RW", "ENTRA_USER_CREATE", "ENTRA_ONBOARDING_PASSWORD"):
        monkeypatch.setenv(f"JASON_{key}_OPENBAO_ROLE_ID_PATH", str(tmp_path/"missing-role"))
        monkeypatch.setenv(f"JASON_{key}_OPENBAO_SECRET_ID_PATH", str(tmp_path/"missing-secret"))
    caps, _, status = registration()
    assert status.enabled_capabilities == ()
    assert set(status.blocked_capabilities) == {IT_GLUE_NOTES, ENTRA_USER_CREATE}
    assert all(x.lifecycle_status == CapabilityLifecycle.BUILDING
               for x in caps.list_all())


def test_exact_profiles_and_nonempty_separate_file_mounts_activate_only_named_capabilities(monkeypatch, tmp_path):
    paths = {}
    for capability, prefix in (
        (IT_GLUE_NOTES, "IT_GLUE_RW"),
        (ENTRA_USER_CREATE, "ENTRA_USER_CREATE"),
        ("entra.initial_password", "ENTRA_ONBOARDING_PASSWORD"),
    ):
        role = tmp_path / f"{prefix}-role"
        secret = tmp_path / f"{prefix}-secret"
        role.write_text(f"{prefix}-role-test")
        secret.write_text(f"{prefix}-secret-test")
        monkeypatch.setenv(f"JASON_{prefix}_OPENBAO_ROLE_ID_PATH", str(role))
        monkeypatch.setenv(f"JASON_{prefix}_OPENBAO_SECRET_ID_PATH", str(secret))
        paths[capability] = (role, secret)
    assert configured_credential_paths() == paths
    monkeypatch.setenv(IT_GLUE_PROFILE_ENV, IT_GLUE_PROFILE)
    monkeypatch.setenv(ENTRA_PROFILE_ENV, ENTRA_PROFILE)
    caps, providers, status = registration()
    assert set(status.enabled_capabilities) == {IT_GLUE_NOTES, ENTRA_USER_CREATE}
    assert set(status.enabled_providers) == {
        "it_glue_configuration_note_update", "microsoft_graph_standard_user_create"
    }
    assert all(x.lifecycle_status is CapabilityLifecycle.ACTIVE for x in caps.list_all())
    assert all(x.lifecycle_status is ProviderLifecycle.AVAILABLE for x in providers.list_all())
    for cap in caps.list_all():
        assert cap.approval.required
        assert cap.client_isolation_required
        assert cap.metadata["mcp_action_enabled"] == "true"
        assert cap.metadata["conversation_authenticated_imperative_is_approval"] == "true"
    paths[ENTRA_USER_CREATE][0].write_text("")
    _, _, disabled = registration()
    assert disabled.enabled_capabilities == (IT_GLUE_NOTES,)
    assert disabled.blocked_capabilities == (ENTRA_USER_CREATE,)


def test_unknown_profile_does_not_inherit_write_grants(monkeypatch, tmp_path):
    monkeypatch.setenv(IT_GLUE_PROFILE_ENV, "true")
    monkeypatch.setenv(ENTRA_PROFILE_ENV, "all-permissions")
    caps, _, status = registration()
    assert not status.enabled_capabilities
    assert not status.blocked_capabilities
    assert all(x.lifecycle_status is CapabilityLifecycle.BUILDING
               for x in caps.list_all())
