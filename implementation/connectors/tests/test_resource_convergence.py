from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorResult
from connectors.core.relationships import VerificationState
from connectors.resource_convergence import (
    GovernedResourceExecutor,
    IdentityEvidence,
    ResourceConvergenceError,
    build_configuration_device_plan,
    build_configuration_device_relationship_evidence,
    build_relationship_evidence,
)


@dataclass
class RecordingConnector:
    provider_name: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={"ok": True},
        )


def context(organization_id="org-208"):
    return ConnectorContext(
        correlation_id="corr-1",
        principal_id="principal-1",
        organization_id=organization_id,
        client_id="client-208",
        capability="resource.convergence",
        mode="observe",
    )


def test_plan_uses_existing_resource_gateway_and_bounded_connectors():
    plan = build_configuration_device_plan(
        organization_id="org-208",
        configuration_id="42",
        search_hint="device-a",
        candidate_limit=3,
    )
    assert plan.reads[0].invocation.capability == "it_glue.entity.get"
    assert plan.reads[0].invocation.arguments == {
        "entity": "Configurations",
        "entity_id": "42",
    }
    assert plan.reads[1].invocation.capability == "datto_rmm.device.search"
    assert plan.reads[1].invocation.arguments == {
        "search": "device-a",
        "page": 1,
        "max": 3,
    }


def test_plan_rejects_unbounded_candidate_count():
    with pytest.raises(ResourceConvergenceError, match="between 1 and 5"):
        build_configuration_device_plan(
            organization_id="org-208",
            configuration_id="42",
            search_hint="device-a",
            candidate_limit=100,
        )


def test_executor_preserves_active_organization_context():
    it_glue = RecordingConnector("it_glue", frozenset({"it_glue.entity.get"}))
    datto = RecordingConnector("datto_rmm", frozenset({"datto_rmm.device.search"}))
    executor = GovernedResourceExecutor({"it_glue": it_glue, "datto_rmm": datto})
    plan = build_configuration_device_plan(
        organization_id="org-208",
        configuration_id="42",
        search_hint="device-a",
    )
    first = executor.execute(plan.reads[0].query, context())
    second = executor.execute(plan.reads[1].query, context())
    assert first.provider == "it_glue"
    assert second.provider == "datto_rmm"
    assert it_glue.requests[0].context.organization_id == "org-208"
    assert datto.requests[0].context.organization_id == "org-208"
    assert it_glue.requests[0].context.correlation_id == "corr-1"
    assert datto.requests[0].context.correlation_id == "corr-1"


def test_executor_denies_cross_organization_query():
    connector = RecordingConnector("it_glue", frozenset({"it_glue.entity.get"}))
    executor = GovernedResourceExecutor({"it_glue": connector})
    plan = build_configuration_device_plan(
        organization_id="org-999",
        configuration_id="42",
        search_hint="device-a",
    )
    with pytest.raises(ResourceConvergenceError, match="exactly match"):
        executor.execute(plan.reads[0].query, context("org-208"))


def test_corroborated_identity_evidence_builds_relationship_evidence():
    configuration = IdentityEvidence(
        provider="it_glue",
        resource_type="configuration",
        external_id="42",
        organization_id="org-208",
        attributes={"serial_number": "ABC123", "name": "device-a"},
    )
    device = IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id="device-1",
        organization_id="org-208",
        attributes={"serial_number": "abc123", "name": "DEVICE-A"},
    )
    evidence = build_configuration_device_relationship_evidence(
        configuration=configuration,
        device=device,
        matched_attributes=("serial_number", "name"),
        confidence=0.98,
    )
    assert evidence.canonical_relationship == "represents"
    assert evidence.verification is VerificationState.CORROBORATED
    assert evidence.source.provider == "it_glue"
    assert evidence.target.provider == "datto_rmm"
    assert evidence.metadata == {"matched_attributes": "serial_number,name"}


def test_match_fails_closed_on_inconsistent_attribute():
    configuration = IdentityEvidence(
        provider="it_glue",
        resource_type="configuration",
        external_id="42",
        organization_id="org-208",
        attributes={"serial_number": "ABC123"},
    )
    device = IdentityEvidence(
        provider="datto_rmm",
        resource_type="device",
        external_id="device-1",
        organization_id="org-208",
        attributes={"serial_number": "XYZ999"},
    )
    with pytest.raises(ResourceConvergenceError, match="inconsistent"):
        build_configuration_device_relationship_evidence(
            configuration=configuration,
            device=device,
            matched_attributes=("serial_number",),
            confidence=0.5,
        )


def test_provider_neutral_evidence_supports_microsoft_and_autotask():
    source = IdentityEvidence(
        provider="microsoft_graph",
        resource_type="user",
        external_id="entra-user-1",
        organization_id="org-208",
        attributes={"email": "User@Example.com"},
        source_authority="graph-user-read",
    )
    target = IdentityEvidence(
        provider="autotask",
        resource_type="contact",
        external_id="contact-7",
        organization_id="org-208",
        attributes={"email": "user@example.com"},
        source_authority="autotask-contact-read",
    )
    observed = datetime(2026, 8, 9, 19, 0, tzinfo=timezone.utc)
    evidence = build_relationship_evidence(
        source=source,
        target=target,
        matched_attributes=("email",),
        canonical_relationship="maps_to",
        confidence=0.96,
        observed_at=observed,
    )
    assert evidence.source.provider == "microsoft_graph"
    assert evidence.target.provider == "autotask"
    assert evidence.canonical_relationship == "maps_to"
    assert evidence.observed_at == observed
    assert evidence.source_authority == "central-orchestrator:graph-user-read+autotask-contact-read"


def test_provider_neutral_evidence_denies_cross_organization_correlation():
    source = IdentityEvidence(
        provider="aws",
        resource_type="account",
        external_id="111111111111",
        organization_id="org-208",
        attributes={"domain": "example.com"},
    )
    target = IdentityEvidence(
        provider="microsoft_graph",
        resource_type="tenant",
        external_id="tenant-2",
        organization_id="org-999",
        attributes={"domain": "example.com"},
    )
    with pytest.raises(ResourceConvergenceError, match="Cross-organization"):
        build_relationship_evidence(
            source=source,
            target=target,
            matched_attributes=("domain",),
            canonical_relationship="maps_to",
            confidence=0.8,
        )


def test_provider_neutral_evidence_requires_unique_matching_attributes():
    source = IdentityEvidence("it_glue", "configuration", "1", "org-208", {"name": "host"})
    target = IdentityEvidence("datto_rmm", "device", "2", "org-208", {"name": "host"})
    with pytest.raises(ResourceConvergenceError, match="unique"):
        build_relationship_evidence(
            source=source,
            target=target,
            matched_attributes=("name", "name"),
            confidence=0.9,
        )


def test_provider_neutral_evidence_rejects_naive_timestamp():
    source = IdentityEvidence("it_glue", "configuration", "1", "org-208", {"name": "host"})
    target = IdentityEvidence("datto_rmm", "device", "2", "org-208", {"name": "host"})
    with pytest.raises(ResourceConvergenceError, match="timezone-aware"):
        build_relationship_evidence(
            source=source,
            target=target,
            matched_attributes=("name",),
            confidence=0.9,
            observed_at=datetime(2026, 8, 9, 19, 0),
        )
