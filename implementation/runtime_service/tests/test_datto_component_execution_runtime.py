from datetime import datetime, timezone

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
        target_uid="device-uid-1",
        target_class="workstation",
        target_deleted=False,
        target_suspended=False,
    ):
        self.calls = []
        self.get_status = get_status
        self.get_uid = get_uid
        self.target_uid = target_uid
        self.target_class = target_class
        self.target_deleted = target_deleted
        self.target_suspended = target_suspended

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

        if method == "PUT":
            return {
                "uid": "job-uid-1",
            }

        if method == "GET" and "/api/v2/device/" in url:
            return {
                "uid": self.target_uid,
                "deviceType": {
                    "category": self.target_class,
                    "type": self.target_class,
                },
                "deleted": self.target_deleted,
                "suspended": self.target_suspended,
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
    target_uid="device-uid-1",
    target_class="workstation",
    target_deleted=False,
    target_suspended=False,
):
    transport = Transport(
        get_status=get_status,
        get_uid=get_uid,
        target_uid=target_uid,
        target_class=target_class,
        target_deleted=target_deleted,
        target_suspended=target_suspended,
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


@pytest.mark.parametrize(
    "override",
    [
        {
            "allowlist_name": "other-component",
        },
        {
            "variables": {
                "arbitrary": "not allowed",
            },
        },
    ],
)
def test_execution_fails_closed_on_invalid_component_scope(
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


def test_managed_target_outside_original_pilot_is_revalidated_and_executes(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        target_uid="other-device",
        target_class="workstation",
    )

    result = value.execute(
        execution_request(
            device_uid="other-device",
            device_class="workstation",
        )
    )

    assert result.data["readback_verified"] is True
    assert [call["method"] for call in transport.calls] == [
        "GET",
        "PUT",
        "GET",
    ]
    assert transport.calls[0]["url"].endswith(
        "/api/v2/device/other-device"
    )
    assert transport.calls[1]["url"].endswith(
        "/api/v2/device/other-device/quickjob"
    )
    assert any(
        event[0] == "connector.target.verified"
        for event in audit.events
    )


def test_target_revalidation_uid_mismatch_fails_before_mutation(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        target_uid="different-device",
    )

    with pytest.raises(
        DattoRmmComponentExecutionVerificationError
    ):
        value.execute(
            execution_request(device_uid="other-device")
        )
    assert [call["method"] for call in transport.calls] == [
        "GET",
    ]
    assert not any(
        event[0] == "connector.mutation.requested"
        for event in audit.events
    )


def test_target_revalidation_class_mismatch_fails_before_mutation(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        target_uid="other-device",
        target_class="workstation",
    )

    with pytest.raises(
        DattoRmmComponentExecutionVerificationError
    ):
        value.execute(
            execution_request(
                device_uid="other-device",
                device_class="server",
            )
        )
    assert [call["method"] for call in transport.calls] == [
        "GET",
    ]
    assert not any(
        event[0] == "connector.mutation.requested"
        for event in audit.events
    )


def test_inactive_target_fails_before_mutation(monkeypatch):
    mock_access_token(monkeypatch)

    value, transport, audit = connector(
        target_uid="other-device",
        target_class="workstation",
        target_suspended=True,
    )

    with pytest.raises(
        DattoRmmComponentExecutionVerificationError
    ):
        value.execute(
            execution_request(device_uid="other-device")
        )

    assert [call["method"] for call in transport.calls] == ["GET"]


def test_dynamic_catalog_variable_contract_is_enforced(monkeypatch):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    result = value.execute(
        execution_request(
            variables={"Mode": "Safe"},
            variable_policies=[
                {
                    "name": "Mode",
                    "variable_type": "string",
                    "required": False,
                    "maximum_length": 64,
                },
            ],
        )
    )

    assert result.data["readback_verified"] is True
    assert transport.calls[1]["json"]["jobComponent"]["variables"] == [
        {"name": "Mode", "value": "Safe"},
    ]


def test_dynamic_catalog_variable_contract_rejects_undeclared_input(
    monkeypatch,
):
    mock_access_token(monkeypatch)

    value, transport, audit = connector()

    with pytest.raises(PermissionError):
        value.execute(
            execution_request(
                variables={"Other": "value"},
                variable_policies=[
                    {
                        "name": "Mode",
                        "variable_type": "string",
                        "required": False,
                        "maximum_length": 64,
                    },
                ],
            )
        )

    assert transport.calls == []
