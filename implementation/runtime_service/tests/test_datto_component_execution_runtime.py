from datetime import datetime, timezone

from types import SimpleNamespace

import pytest

from connectors.core.contracts import (
    ConnectorContext,
    ConnectorRequest,
)
from connectors.datto_rmm.auth import DattoRmmAccessToken
from jason_runtime import datto_component_execution as module
from jason_runtime.datto_component_execution import (
    AUTOMATION_COMPONENT_EXECUTE,
    DATTO_COMPONENT_EXECUTION_PROFILE,
    DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
    DATTO_EXECUTION_ALLOWLIST_NAME_ENV,
    DATTO_EXECUTION_COMPONENT_NAME_ENV,
    DATTO_EXECUTION_COMPONENT_UID_ENV,
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    DATTO_EXECUTION_DEVICE_CLASS_ENV,
    DATTO_EXECUTION_DEVICE_UID_ENV,
    DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
    DattoApprovedComponent,
    DattoComponentExecutionPilot,
    DattoRmmComponentExecutionConnector,
    DattoRmmComponentExecutionVerificationError,
    configured_pilot,
    register_datto_component_execution_runtime_foundation,
)
from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)


def registries():
    return (
        CapabilityRegistryService(
            registry=InMemoryCapabilityRegistry()
        ),
        ExecutionProviderRegistryService(
            registry=InMemoryExecutionProviderRegistry()
        ),
    )


def clear_env(monkeypatch):
    for name in (
        DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
        DATTO_EXECUTION_ALLOWLIST_NAME_ENV,
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        DATTO_EXECUTION_DEVICE_UID_ENV,
        DATTO_EXECUTION_DEVICE_CLASS_ENV,
    ):
        monkeypatch.delenv(
            name,
            raising=False,
        )


def enable_env(monkeypatch):
    monkeypatch.setenv(
        DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
        DATTO_COMPONENT_EXECUTION_PROFILE,
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_ALLOWLIST_NAME_ENV,
        "pilot-diagnostic",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        "component-uid-1",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
        "Pilot Diagnostic",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_DEVICE_UID_ENV,
        "device-uid-1",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_DEVICE_CLASS_ENV,
        "workstation",
    )


def enable_multi_component_env(monkeypatch):
    monkeypatch.setenv(
        DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
        DATTO_COMPONENT_EXECUTION_PROFILE,
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_ALLOWLIST_NAME_ENV,
        "pilot-diagnostic",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-uid-1","name":"Pilot Diagnostic","approval_mode":"standing_safe"},'
        '{"uid":"component-uid-2","name":"Secondary Diagnostic","approval_mode":"per_run"}]',
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_DEVICE_UID_ENV,
        "device-uid-1",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_DEVICE_CLASS_ENV,
        "workstation",
    )


def test_execution_foundation_is_dormant_by_default(
    monkeypatch,
):
    clear_env(monkeypatch)

    capabilities, providers = registries()

    state = register_datto_component_execution_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is False

    capability = capabilities.get(
        capability_name=AUTOMATION_COMPONENT_EXECUTE,
        version="1.0",
    )

    provider = providers.get(
        DATTO_RMM_COMPONENT_EXECUTION_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.BUILDING
    )

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.PLANNED
    )


def test_exact_profile_activates_component_execution(
    monkeypatch,
):
    enable_env(monkeypatch)

    capabilities, providers = registries()

    state = register_datto_component_execution_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is True

    capability = capabilities.get_current(
        capability_name=AUTOMATION_COMPONENT_EXECUTE
    )

    provider = providers.get(
        DATTO_RMM_COMPONENT_EXECUTION_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.ACTIVE
    )

    assert capability.approval.required is True
    assert capability.maximum_attempts == 1
    assert capability.idempotency_key_required is True

    assert (
        capability.metadata["mcp_action_enabled"]
        == "true"
    )

    assert (
        capability.metadata[
            "conversation_authenticated_imperative_is_approval"
        ]
        == "true"
    )

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.AVAILABLE
    )

    assert (
        provider.health_status
        is ProviderHealth.HEALTHY
    )

    assert (
        provider.approval_status
        is ProviderApproval.APPROVED
    )


def test_durable_components_alone_do_not_activate_legacy_pilot(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setattr(
        module,
        "configured_datto_components",
        lambda: (object(),),
    )

    assert configured_pilot() is None


def test_partial_legacy_pilot_still_fails_closed_with_durable_components(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_ALLOWLIST_NAME_ENV,
        "pilot-diagnostic",
    )
    monkeypatch.setattr(
        module,
        "configured_datto_components",
        lambda: (object(),),
    )

    with pytest.raises(
        module.DattoRmmComponentExecutionActivationError,
        match="incomplete",
    ):
        configured_pilot()


def test_json_component_scope_is_authoritative(monkeypatch):
    clear_env(monkeypatch)
    enable_multi_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        "legacy-component",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
        "Legacy Component",
    )

    pilot = configured_pilot()

    assert pilot is not None
    assert [item.uid for item in pilot.components] == [
        "component-uid-1",
        "component-uid-2",
    ]
    assert pilot.components[0].requires_explicit_approval is False
    assert pilot.components[1].requires_explicit_approval is True


class Secrets:
    def resolve(
        self,
        logical_name,
        context,
    ):
        del context

        assert logical_name == "datto_rmm.execution"

        return {
            "api_url": "https://example.invalid",
            "api_key": "synthetic-key",
            "api_secret": "synthetic-secret",
        }


class Audit:
    def __init__(self):
        self.events = []

    def record(
        self,
        event_type,
        context,
        details,
    ):
        del context

        self.events.append(
            (
                event_type,
                dict(details),
            )
        )


class Transport:
    def __init__(
        self,
        *,
        get_status="completed",
        get_uid="job-uid-1",
    ):
        self.calls = []
        self.get_status = get_status
        self.get_uid = get_uid

    def request(
        self,
        *,
        method,
        url,
        headers,
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
                "timeout_seconds": timeout_seconds,
            }
        )

        if method == "GET" and "/api/v2/device/" in url:
            return {
                "uid": url.rsplit("/", 1)[-1],
                "deleted": False,
                "suspended": False,
            }

        if method == "PUT":
            return {
                "uid": "job-uid-1",
            }

        if method == "GET":
            return {
                "uid": self.get_uid,
                "status": self.get_status,
                "name": "Jason - Pilot Diagnostic",
            }

        raise AssertionError("unexpected transport call")


def execution_request(
    **overrides,
):
    arguments = {
        "allowlist_name": "pilot-diagnostic",
        "device_uid": "device-uid-1",
        "device_class": "workstation",
        "component_uid": "component-uid-1",
        "component_name": "Pilot Diagnostic",
        "variables": {},
    }

    arguments.update(overrides)

    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-test",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="datto_rmm.component.execute",
            mode="execute",
        ),
        arguments=arguments,
    )


def connector(
    *,
    get_status="completed",
    get_uid="job-uid-1",
):
    transport = Transport(
        get_status=get_status,
        get_uid=get_uid,
    )
    audit = Audit()

    value = DattoRmmComponentExecutionConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
        pilot=DattoComponentExecutionPilot(
            allowlist_name="pilot-diagnostic",
            components=(
                DattoApprovedComponent(
                    uid="component-uid-1",
                    name="Pilot Diagnostic",
                ),
                DattoApprovedComponent(
                    uid="component-uid-2",
                    name="Secondary Diagnostic",
                ),
            ),
            device_uid="device-uid-1",
            device_class="workstation",
        ),
        sleeper=lambda _: None,
        maximum_status_reads=1,
        status_interval_seconds=0,
    )

    return value, transport, audit


def mock_access_token(monkeypatch):
    monkeypatch.setattr(
        module,
        "acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken(
            access_token="synthetic-token",
            token_type="Bearer",
        ),
    )


def test_live_connector_issues_one_quickjob_and_verifies_job(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    result = value.execute(
        execution_request()
    )

    assert result.data["readback_verified"] is True
    assert result.data["completion_verified"] is True
    assert result.data["job_uid"] == "job-uid-1"
    assert result.data["job_status"] == "completed"

    assert [
        call["method"]
        for call in transport.calls
    ] == [
        "GET",
        "PUT",
        "GET",
    ]

    assert (
        transport.calls[1]["json"]["jobComponent"][
            "componentUid"
        ]
        == "component-uid-1"
    )

    assert any(
        event[0]
        == "connector.mutation.verified"
        for event in audit.events
    )


def test_second_allowlisted_component_uses_exact_provider_uid(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    result = value.execute(
        execution_request(
            component_uid="component-uid-2",
            component_name="Secondary Diagnostic",
        )
    )

    assert result.data["readback_verified"] is True
    assert (
        transport.calls[1]["json"]["jobComponent"][
            "componentUid"
        ]
        == "component-uid-2"
    )
    assert any(
        event[0]
        == "connector.mutation.verified"
        for event in audit.events
    )


def test_async_quickjob_returns_durable_accepted_job_reference(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        get_status="running",
    )

    result = value.execute(
        execution_request()
    )

    assert result.data["status"] == "accepted"
    assert result.data["job_uid"] == "job-uid-1"
    assert result.data["job_status"] == "running"
    assert result.data["readback_verified"] is True
    assert result.data["completion_verified"] is False
    assert result.warnings

    assert [
        call["method"]
        for call in transport.calls
    ] == [
        "GET",
        "PUT",
        "GET",
    ]

    assert any(
        event[0]
        == "connector.mutation.accepted"
        for event in audit.events
    )


def test_quickjob_readback_uid_mismatch_fails_closed(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        get_status="running",
        get_uid="different-job-uid",
    )

    with pytest.raises(
        DattoRmmComponentExecutionVerificationError
    ):
        value.execute(
            execution_request()
        )

    assert [
        call["method"]
        for call in transport.calls
    ] == [
        "GET",
        "PUT",
        "GET",
    ]

    assert any(
        event[0]
        == "connector.mutation.failed"
        for event in audit.events
    )


def test_quickjob_terminal_failure_fails_closed(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        get_status="failed",
    )

    with pytest.raises(
        DattoRmmComponentExecutionVerificationError
    ):
        value.execute(
            execution_request()
        )

    assert [
        call["method"]
        for call in transport.calls
    ] == [
        "GET",
        "PUT",
        "GET",
    ]

    assert any(
        event[0]
        == "connector.mutation.failed"
        for event in audit.events
    )


def test_execution_accepts_different_verified_managed_target(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    result = value.execute(
        execution_request(
            device_uid="other-managed-device",
        )
    )

    assert result.data["device_uid"] == "other-managed-device"
    assert transport.calls[0]["url"].endswith(
        "/api/v2/device/other-managed-device"
    )
    assert transport.calls[1]["url"].endswith(
        "/api/v2/device/other-managed-device/quickjob"
    )
    assert any(
        event[0] == "connector.target.verified"
        for event in audit.events
    )


@pytest.mark.parametrize(
    "override",
    [
        {
            "allowlist_name": "other-component",
        },
        {
            "device_class": "server",
        },
        {
            "variables": {
                "arbitrary": "not allowed",
            },
        },
    ],
)
def test_execution_fails_closed_outside_exact_pilot(
    monkeypatch,
    override,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    with pytest.raises(
        (
            PermissionError,
            ValueError,
        )
    ):
        value.execute(
            execution_request(
                **override
            )
        )

    assert transport.calls == []


def test_governed_prepare_is_side_effect_free_and_secret_free(monkeypatch):
    mock_access_token(monkeypatch)
    value, transport, audit = connector()

    prepared = value.prepare_governed_execution(execution_request())

    assert [call["method"] for call in transport.calls] == ["GET"]
    assert prepared.resource_identifier == "device-uid-1"
    assert prepared.action_method == "PUT"
    assert prepared.normalized_path.endswith("/api/v2/device/device-uid-1/quickjob")
    assert prepared.payload["jobComponent"]["componentUid"] == "component-uid-1"
    assert prepared.symbolic_resolutions["component"] == {
        "symbolic": "Pilot Diagnostic",
        "resolved": "component-uid-1",
    }
    material = repr((prepared.payload, prepared.parameters, prepared.symbolic_resolutions))
    assert "synthetic-token" not in material
    assert "synthetic-key" not in material
    assert "synthetic-secret" not in material


def test_governed_execution_rejects_tampered_target_before_quickjob(monkeypatch):
    from dataclasses import replace

    mock_access_token(monkeypatch)
    value, transport, audit = connector()
    prepared = value.prepare_governed_execution(execution_request())
    tampered = replace(prepared, resource_identifier="different-device")

    with pytest.raises(PermissionError, match="target changed"):
        value.execute_governed_execution(tampered)

    assert [call["method"] for call in transport.calls] == ["GET"]


def test_autonomy_component_execution_uses_durable_scope_without_legacy_pilot(monkeypatch):
    from jason_runtime.datto_component_execution import DattoRmmComponentExecutionConnector
    from jason_runtime.datto_component_scope import DattoApprovedComponent
    from connectors.core.contracts import ConnectorContext, ConnectorRequest

    class Secrets:
        def resolve(self, logical_secret, context):
            return {
                "api_url": "https://example.invalid",
                "api_key": "client",
                "api_secret": "secret",
            }

    class Transport:
        def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
            if method == "GET" and "/api/v2/device/" in url:
                return {"uid": "device-1", "deleted": False, "suspended": False}
            raise AssertionError((method, url))

    monkeypatch.setattr(
        "jason_runtime.datto_component_execution.acquire_access_token",
        lambda **kwargs: SimpleNamespace(token_type="Bearer", access_token="token"),
    )

    connector = DattoRmmComponentExecutionConnector(
        secrets=Secrets(),
        transport=Transport(),
        audit=SimpleNamespace(record=lambda *args, **kwargs: None),
        pilot=None,
        autonomy_enabled=True,
        autonomy_components=(
            DattoApprovedComponent(
                uid="component-safe",
                name="Safe Diagnostic",
                approval_mode="standing_safe",
            ),
        ),
    )
    request = ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-autonomy-component",
            principal_id="jason-autonomy-worker",
            organization_id="aot",
            client_id=None,
            capability="datto_rmm.component.execute",
            mode="execute",
        ),
        arguments={
            "device_uid": "device-1",
            "component_uid": "component-safe",
            "component_name": "Safe Diagnostic",
            "variables": {},
            "job_name": "Jason autonomous test",
        },
    )

    prepared = connector.prepare_governed_execution(request)

    assert prepared.resource_identifier == "device-1"
    assert prepared.parameters["allowlist_name"] == "aot-approved-components"
    assert prepared.parameters["device_class"] == "managed_endpoint"


def test_autonomy_component_execution_rejects_per_run_component(monkeypatch):
    from jason_runtime.datto_component_execution import DattoRmmComponentExecutionConnector
    from jason_runtime.datto_component_scope import DattoApprovedComponent
    from connectors.core.contracts import ConnectorContext, ConnectorRequest

    connector = DattoRmmComponentExecutionConnector(
        secrets=SimpleNamespace(),
        transport=SimpleNamespace(),
        audit=SimpleNamespace(record=lambda *args, **kwargs: None),
        pilot=None,
        autonomy_enabled=True,
        autonomy_components=(
            DattoApprovedComponent(
                uid="component-risky",
                name="Risky Component",
                approval_mode="per_run",
            ),
        ),
    )
    request = ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-autonomy-component-risky",
            principal_id="jason-autonomy-worker",
            organization_id="aot",
            client_id=None,
            capability="datto_rmm.component.execute",
            mode="execute",
        ),
        arguments={
            "device_uid": "device-1",
            "component_uid": "component-risky",
            "component_name": "Risky Component",
            "variables": {},
        },
    )

    with pytest.raises(PermissionError, match="DATTO_COMPONENT_AUTONOMY_REQUIRES_STANDING_SAFE"):
        connector.prepare_governed_execution(request)
