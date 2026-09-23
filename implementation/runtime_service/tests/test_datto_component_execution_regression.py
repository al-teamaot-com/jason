import pytest

from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)
from jason_runtime.datto_component_scope import (
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    configured_datto_components,
)


SERVICE_COMPONENT_NAME = (
    "Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1"
)
SERVICE_COMPONENT_UID = "2b49d490-bcae-4825-b31e-c4f1be881ae5"


def test_stale_server_uid_is_canonicalized_for_verified_service_diagnostic(
    monkeypatch,
):
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"stale-provider-uid","name":"'
        + SERVICE_COMPONENT_NAME
        + '","approval_mode":"standing_safe"}]',
    )

    components = configured_datto_components()

    assert len(components) == 1
    assert components[0].uid == SERVICE_COMPONENT_UID
    assert components[0].name == SERVICE_COMPONENT_NAME
    assert components[0].requires_explicit_approval is False


def _service_policy():
    entry = ComponentAllowlistEntry(
        allowlist_name="service-diagnostic",
        canonical_component_id="datto:service-diagnostic:" + SERVICE_COMPONENT_UID,
        display_name=SERVICE_COMPONENT_NAME,
        provider_component_uid=SERVICE_COMPONENT_UID,
        allowed_target_classes=frozenset({"workstation", "server"}),
        variable_policies=(),
        requires_per_run_approval=False,
        status="active",
    )
    return DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(entries=(entry,))
    )


def test_service_name_variable_is_bounded_and_allowed():
    prepared = _service_policy().prepare(
        allowlist_name="service-diagnostic",
        device_uid="device-1",
        device_class="workstation",
        component_uid=SERVICE_COMPONENT_UID,
        variables={"ServiceName": "EndpointProtectionService"},
        observed_component_name=SERVICE_COMPONENT_NAME,
    )

    assert prepared.normalized_variables == {
        "ServiceName": "EndpointProtectionService"
    }
    assert prepared.provider_request.body["jobComponent"]["variables"] == [
        {
            "name": "ServiceName",
            "value": "EndpointProtectionService",
        }
    ]


def test_service_diagnostic_rejects_unknown_variable():
    with pytest.raises(PermissionError):
        _service_policy().prepare(
            allowlist_name="service-diagnostic",
            device_uid="device-1",
            device_class="workstation",
            component_uid=SERVICE_COMPONENT_UID,
            variables={"ArbitraryCommand": "whoami"},
            observed_component_name=SERVICE_COMPONENT_NAME,
        )


def test_service_name_variable_enforces_length_bound():
    with pytest.raises(ValueError):
        _service_policy().prepare(
            allowlist_name="service-diagnostic",
            device_uid="device-1",
            device_class="workstation",
            component_uid=SERVICE_COMPONENT_UID,
            variables={"ServiceName": "x" * 257},
            observed_component_name=SERVICE_COMPONENT_NAME,
        )
