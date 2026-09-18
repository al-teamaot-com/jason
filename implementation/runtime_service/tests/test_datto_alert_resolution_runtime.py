from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.datto_rmm.auth import DattoRmmAccessToken
from jason_runtime import datto_alert_resolution as module
from jason_runtime.datto_alert_resolution import (
    DATTO_ALERT_RESOLUTION_PROFILE,
    DATTO_ALERT_RESOLUTION_PROFILE_ENV,
    DATTO_RMM_ALERT_RESOLUTION_PROVIDER,
    ENDPOINT_ALERT_RESOLVE,
    DattoRmmAlertResolutionConnector,
    DattoRmmAlertResolutionVerificationError,
    register_datto_alert_resolution_runtime_foundation,
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


ALERT_UID = "a162d5e0-1d84-48f3-a67f-2acf1b18c0e6"
DEVICE_UID = "69571572-83f7-1e33-9cdf-01717d4e74a4"


def registries():
    return (
        CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
        ExecutionProviderRegistryService(
            registry=InMemoryExecutionProviderRegistry()
        ),
    )


def test_foundation_is_dormant_by_default(monkeypatch):
    monkeypatch.delenv(DATTO_ALERT_RESOLUTION_PROFILE_ENV, raising=False)
    capabilities, providers = registries()

    state = register_datto_alert_resolution_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is False
    assert capabilities.get(
        capability_name=ENDPOINT_ALERT_RESOLVE,
        version="1.0",
    ).lifecycle_status is CapabilityLifecycle.BUILDING
    assert providers.get(
        DATTO_RMM_ALERT_RESOLUTION_PROVIDER
    ).lifecycle_status is ProviderLifecycle.PLANNED


def test_exact_profile_activates_alert_resolution(monkeypatch):
    monkeypatch.setenv(
        DATTO_ALERT_RESOLUTION_PROFILE_ENV,
        DATTO_ALERT_RESOLUTION_PROFILE,
    )
    capabilities, providers = registries()

    state = register_datto_alert_resolution_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is True
    capability = capabilities.get_current(
        capability_name=ENDPOINT_ALERT_RESOLVE
    )
    provider = providers.get(DATTO_RMM_ALERT_RESOLUTION_PROVIDER)
    assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
    assert capability.approval.required is True
    assert capability.maximum_attempts == 1
    assert capability.metadata["mcp_action_enabled"] == "true"
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED


class Secrets:
    def resolve(self, logical_name, context):
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

    def record(self, event_type, context, details):
        del context
        self.events.append((event_type, dict(details)))


class Transport:
    def __init__(self, *, before_resolved=False, after_resolved=True):
        self.before_resolved = before_resolved
        self.after_resolved = after_resolved
        self.calls = []
        self.read_count = 0

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
        if method == "POST":
            return {}
        if method != "GET":
            raise AssertionError("unexpected transport method")

        self.read_count += 1
        resolved = (
            self.before_resolved
            if self.read_count == 1
            else self.after_resolved
        )
        return {
            "alertUid": ALERT_UID,
            "resolved": resolved,
            "alertSourceInfo": {"deviceUid": DEVICE_UID},
        }


def request(**overrides):
    args = {
        "alert_uid": ALERT_UID,
        "device_uid": DEVICE_UID,
    }
    args.update(overrides)
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-alert-resolve",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="datto_rmm.alert.resolve",
            mode="execute",
        ),
        arguments=args,
    )


def build_connector(*, before_resolved=False, after_resolved=True):
    transport = Transport(
        before_resolved=before_resolved,
        after_resolved=after_resolved,
    )
    audit = Audit()
    connector = DattoRmmAlertResolutionConnector(
        secrets=Secrets(),
        transport=transport,
        audit=audit,
    )
    return connector, transport, audit


def mock_access_token(monkeypatch):
    monkeypatch.setattr(
        module,
        "acquire_access_token",
        lambda *, credentials: DattoRmmAccessToken(
            access_token="synthetic-token",
            token_type="Bearer",
        ),
    )


def test_resolve_issues_exactly_one_post_and_verifies_readback(monkeypatch):
    mock_access_token(monkeypatch)
    connector, transport, audit = build_connector()

    result = connector.execute(request())

    assert result.data["resolved"] is True
    assert result.data["mutation_performed"] is True
    assert result.data["readback_verified"] is True
    assert [call["method"] for call in transport.calls] == [
        "GET",
        "POST",
        "GET",
    ]
    assert transport.calls[1]["url"].endswith(
        f"/api/v2/alert/{ALERT_UID}/resolve"
    )
    assert transport.calls[1]["json"] is None
    assert any(
        name == "connector.mutation.verified"
        for name, _ in audit.events
    )


def test_already_resolved_is_idempotent_and_does_not_post(monkeypatch):
    mock_access_token(monkeypatch)
    connector, transport, _ = build_connector(before_resolved=True)

    result = connector.execute(request())

    assert result.data["already_resolved"] is True
    assert result.data["mutation_performed"] is False
    assert [call["method"] for call in transport.calls] == ["GET"]


def test_device_mismatch_fails_before_mutation(monkeypatch):
    mock_access_token(monkeypatch)
    connector, transport, _ = build_connector()
    transport.request = lambda **kwargs: {
        "alertUid": ALERT_UID,
        "resolved": False,
        "alertSourceInfo": {
            "deviceUid": "11111111-1111-1111-1111-111111111111"
        },
    }

    with pytest.raises(
        DattoRmmAlertResolutionVerificationError,
        match="device UID",
    ):
        connector.execute(request())


def test_unverified_post_read_fails_closed(monkeypatch):
    mock_access_token(monkeypatch)
    connector, transport, _ = build_connector(after_resolved=False)

    with pytest.raises(
        DattoRmmAlertResolutionVerificationError,
        match="resolved=true",
    ):
        connector.execute(request())

    assert [call["method"] for call in transport.calls] == [
        "GET",
        "POST",
        "GET",
    ]


def test_unknown_arguments_are_rejected_before_provider_mutation(monkeypatch):
    mock_access_token(monkeypatch)
    connector, transport, _ = build_connector()

    with pytest.raises(ValueError, match="unsupported"):
        connector.execute(request(resolution_note="not-provider-supported"))

    assert transport.calls == []
