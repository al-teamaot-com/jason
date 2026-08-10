from __future__ import annotations

from connectors.core.contracts import ConnectorResult
from connectors.managed_device_authority import (
    DATTO_MANAGED_DEVICE_AUTHORITY,
    IT_GLUE_DEVICE_DOCUMENTATION_AUTHORITY,
)
from connectors.resource_convergence import IdentityEvidence, ResourceConvergenceError
from connectors.live_convergence import (
    LiveConfigurationDeviceConvergenceRequest,
    LiveConfigurationDeviceConvergenceService,
)


class FakeExecutor:
    def __init__(self, *, wrong_provider: bool = False) -> None:
        self.calls = []
        self.wrong_provider = wrong_provider

    def execute(self, query, context):
        self.calls.append((query, context))
        provider = query.provider
        if self.wrong_provider and provider == "datto_rmm":
            provider = "it_glue"
        return ConnectorResult(
            capability="it_glue.entity.get" if query.provider == "it_glue" else "datto_rmm.device.search",
            provider=provider,
            data={"provider": query.provider},
        )


def it_glue_projector(result: ConnectorResult, organization_id: str) -> IdentityEvidence:
    return IdentityEvidence(
        provider="it_glue",
        resource_type="configuration",
        external_id="cfg-42",
        organization_id=organization_id,
        attributes={"serial": "ABC123", "hostname": "WS-42"},
        source_authority=IT_GLUE_DEVICE_DOCUMENTATION_AUTHORITY,
    )


def datto_projector(result: ConnectorResult, organization_id: str) -> IdentityEvidence:
    return IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id="dev-42",
        organization_id=organization_id,
        attributes={"serial": "abc123", "hostname": "ws-42"},
        source_authority=DATTO_MANAGED_DEVICE_AUTHORITY,
    )


def request(**overrides):
    values = dict(
        organization_id="org-a",
        principal_id="principal-a",
        correlation_id="corr-a",
        configuration_id="42",
        search_hint="WS-42",
        matched_attributes=("serial", "hostname"),
        confidence=0.95,
        candidate_limit=3,
    )
    values.update(overrides)
    return LiveConfigurationDeviceConvergenceRequest(**values)


def test_live_convergence_establishes_datto_authority_and_returns_documentation_evidence() -> None:
    executor = FakeExecutor()
    service = LiveConfigurationDeviceConvergenceService(
        executor=executor,
        it_glue_projector=it_glue_projector,
        datto_projector=datto_projector,
    )
    observation = service.observe(request())

    assert [call[0].provider for call in executor.calls] == ["it_glue", "datto_rmm"]
    assert all(call[1].organization_id == "org-a" for call in executor.calls)
    assert all(call[1].mode == "observe" for call in executor.calls)
    assert observation.managed_device_authority.authoritative_provider == "datto_rmm"
    assert observation.managed_device_authority.device.external_id == "dev-42"
    assert observation.relationship_status == "corroborated"
    assert observation.evidence is not None
    assert observation.evidence.source.provider == "datto_rmm"
    assert observation.evidence.target.provider == "it_glue"
    assert observation.evidence.canonical_relationship == "represented_by"
    assert observation.evidence.metadata == {"matched_attributes": "serial,hostname"}
    assert observation.evidence.confidence == 0.95


def test_live_convergence_rejects_provider_result_mismatch() -> None:
    service = LiveConfigurationDeviceConvergenceService(
        executor=FakeExecutor(wrong_provider=True),
        it_glue_projector=it_glue_projector,
        datto_projector=datto_projector,
    )
    try:
        service.observe(request())
    except ResourceConvergenceError as exc:
        assert "provider result" in str(exc)
    else:
        raise AssertionError("provider mismatch must fail closed")


def test_live_convergence_rejects_projected_cross_tenant_evidence() -> None:
    def wrong_org_projector(result: ConnectorResult, organization_id: str) -> IdentityEvidence:
        evidence = datto_projector(result, organization_id)
        return IdentityEvidence(
            provider=evidence.provider,
            resource_type=evidence.resource_type,
            external_id=evidence.external_id,
            organization_id="org-b",
            attributes=evidence.attributes,
            source_authority=evidence.source_authority,
        )

    service = LiveConfigurationDeviceConvergenceService(
        executor=FakeExecutor(),
        it_glue_projector=it_glue_projector,
        datto_projector=wrong_org_projector,
    )
    try:
        service.observe(request())
    except PermissionError as exc:
        assert "organization mismatch" in str(exc)
    else:
        raise AssertionError("cross-organization projection must fail closed")


def test_unmatched_it_glue_does_not_erase_datto_managed_device_authority() -> None:
    service = LiveConfigurationDeviceConvergenceService(
        executor=FakeExecutor(),
        it_glue_projector=it_glue_projector,
        datto_projector=datto_projector,
    )

    observation = service.observe(request(matched_attributes=("serial", "missing")))

    assert observation.managed_device_authority.authoritative_provider == "datto_rmm"
    assert observation.managed_device_authority.device.external_id == "dev-42"
    assert observation.relationship_status == "unresolved"
    assert observation.relationship_evidence is None
    assert observation.relationship_reason is not None
    assert "absent or inconsistent" in observation.relationship_reason
