from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "datto_rmm_execution_identity_probe.py"
)
SPEC = importlib.util.spec_from_file_location("datto_execution_identity_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_preflight_is_network_and_mutation_safe():
    result = MODULE.preflight()

    assert result["network_contacted"] is False
    assert result["provider_credentials_used"] is False
    assert result["provider_mutation_requests"] == 0
    assert result["component_execution_attempted"] is False
    assert result["runtime_execution_activated"] is False
    assert result["status"] == "credential_safe_preflight"


def test_probe_passes_only_when_auth_succeeds_and_global_settings_reads_are_denied():
    result = MODULE.assess_probe_results(
        system_status=200,
        account_status=403,
        devices_status=403,
        components_status=403,
    )

    assert result["authenticated"] is True
    assert result["global_settings_reads_denied"] is True
    assert result["provider_mutation_requests"] == 0
    assert result["component_execution_attempted"] is False
    assert result["device_visibility_proven"] is False
    assert result["api_component_level_proven"] is False
    assert result["status"] == "pass"


def test_probe_fails_when_system_status_does_not_authenticate():
    result = MODULE.assess_probe_results(
        system_status=401,
        account_status=403,
        devices_status=403,
        components_status=403,
    )

    assert result["authenticated"] is False
    assert result["status"] == "fail"


def test_probe_fails_closed_when_global_settings_account_read_is_accessible():
    result = MODULE.assess_probe_results(
        system_status=200,
        account_status=200,
        devices_status=403,
        components_status=403,
    )

    assert result["global_settings_reads_denied"] is False
    assert result["status"] == "fail"


def test_probe_fails_closed_when_global_settings_device_read_is_accessible():
    result = MODULE.assess_probe_results(
        system_status=200,
        account_status=403,
        devices_status=200,
        components_status=403,
    )

    assert result["global_settings_reads_denied"] is False
    assert result["status"] == "fail"


def test_probe_fails_closed_when_global_settings_component_read_is_accessible():
    result = MODULE.assess_probe_results(
        system_status=200,
        account_status=403,
        devices_status=403,
        components_status=200,
    )

    assert result["global_settings_reads_denied"] is False
    assert result["status"] == "fail"
