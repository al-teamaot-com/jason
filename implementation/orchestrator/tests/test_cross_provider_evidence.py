from datetime import datetime, timezone

import pytest

from connectors.core.relationships import ResourceRef, VerificationState
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.canonical_entity_correlation import (
    CanonicalEntityCorrelationRegistry,
    CanonicalEntityMapping,
    CanonicalEntityType,
    CorrelationBasis,
)
from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.cross_provider_evidence import (
    CrossProviderEvidenceError,
    build_evidence_package,
    plan_correlated_resources,
)
from orchestrator.governed_evidence_cache import FreshnessClass


NOW = datetime(2026, 9, 10, 10, 30, tzinfo=timezone.utc)


def mapping(provider, resource_type, external_id, *, basis=CorrelationBasis.EXPLICIT, confidence=1.0):
    verification = (
        VerificationState.VERIFIED
        if basis in {CorrelationBasis.EXPLICIT, CorrelationBasis.CONFIGURED}
        else VerificationState.CORROBORATED
    )
    return CanonicalEntityMapping(
        canonical_id="endpoint:aot-50282",
        entity_type=CanonicalEntityType.ENDPOINT,
        organization_id="aot",
        resource=ResourceRef(
            provider=provider,
            resource_type=resource_type,
            external_id=external_id,
            organization_id="aot",
        ),
        basis=basis,
        verification=verification,
        confidence=confidence,
        provenance=(f"provider:{provider}", "correlation:test"),
        observed_at=NOW,
    )


def result(provider, capability, provider_capability, data, evidence_id):
    resolution = CapabilityResolutionResult(
        execution_id=f"exec-{provider}",
        correlation_id="corr-ticket-12345",
        capability_name=capability,
        capability_version="1.0.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
        reason_codes=("resolved",),
        eligible_provider_ids=(provider,),
        selected_provider_id=provider,
    )
    return OrchestrationResult(
        execution_id=f"exec-{provider}",
        correlation_id="corr-ticket-12345",
        capability_name=capability,
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("capability_completed",),
        resolution=resolution,
        output={
            "provider": provider,
            "provider_capability": provider_capability,
            "data": data,
            "evidence_ids": (evidence_id,),
        },
        attempts=1,
        provider_id=provider,
    )


def test_autotask_configuration_seed_expands_to_it_glue_and_drmm() -> None:
    registry = CanonicalEntityCorrelationRegistry(
        (
            mapping("autotask", "configuration_item", "ci-77"),
            mapping("it_glue", "configuration", "config-42", basis=CorrelationBasis.CORROBORATED, confidence=0.98),
            mapping("datto_rmm", "device", "device-50282"),
        )
    )
    seed = ResourceRef(
        provider="autotask",
        resource_type="configuration_item",
        external_id="ci-77",
        organization_id="aot",
    )

    plan = plan_correlated_resources(
        seed=seed,
        entity_type=CanonicalEntityType.ENDPOINT,
        registry=registry,
        target_providers=("it_glue", "datto_rmm"),
    )

    assert plan.canonical_id == "endpoint:aot-50282"
    assert {(item.provider, item.external_id) for item in plan.resources} == {
        ("autotask", "ci-77"),
        ("it_glue", "config-42"),
        ("datto_rmm", "device-50282"),
    }
    it_glue_mapping = next(item for item in plan.mappings if item.resource.provider == "it_glue")
    assert it_glue_mapping.authoritative is False
    assert it_glue_mapping.confidence == 0.98


def test_ambiguous_peer_mapping_fails_closed_before_provider_routing() -> None:
    registry = CanonicalEntityCorrelationRegistry(
        (
            mapping("autotask", "configuration_item", "ci-77"),
            mapping("it_glue", "configuration", "config-1", basis=CorrelationBasis.CORROBORATED, confidence=0.9),
            mapping("it_glue", "configuration", "config-2", basis=CorrelationBasis.CORROBORATED, confidence=0.9),
        )
    )
    seed = ResourceRef("autotask", "configuration_item", "ci-77", "aot")

    with pytest.raises(CrossProviderEvidenceError, match="ambiguous"):
        plan_correlated_resources(
            seed=seed,
            entity_type=CanonicalEntityType.ENDPOINT,
            registry=registry,
            target_providers=("it_glue",),
        )


def test_multiple_provider_reads_become_one_sanitized_zero_model_evidence_package() -> None:
    mappings = (
        mapping("autotask", "configuration_item", "ci-77"),
        mapping("it_glue", "configuration", "config-42", basis=CorrelationBasis.CORROBORATED, confidence=0.98),
        mapping("datto_rmm", "device", "device-50282"),
    )
    results = (
        result(
            "autotask",
            "service.ticket.read",
            "autotask.ticket.get",
            {"ticketNumber": "12345", "configurationItemID": "ci-77"},
            "evidence://autotask/ticket/12345",
        ),
        result(
            "it_glue",
            "documentation.configuration.read",
            "it_glue.entity.get",
            {"name": "AOT-50282", "serial": "ABC123"},
            "evidence://itglue/config/42",
        ),
        result(
            "datto_rmm",
            "endpoint.device.read",
            "datto_rmm.device.get",
            {"hostname": "AOT-50282", "online": True},
            "evidence://datto/device/device-50282",
        ),
    )

    package = build_evidence_package(
        correlation_id="corr-ticket-12345",
        principal_id="person-al",
        organization_id="aot",
        client_id="aot",
        results=results,
        freshness_by_capability={
            "service.ticket.read": FreshnessClass.TRANSACTIONAL,
            "documentation.configuration.read": FreshnessClass.SLOW_CHANGE,
            "endpoint.device.read": FreshnessClass.REALTIME,
        },
        mappings=mappings,
        created_at=NOW,
    )

    assert {item.provider_id for item in package.observations} == {
        "autotask",
        "it_glue",
        "datto_rmm",
    }
    assert package.canonical_ids == ("endpoint:aot-50282",)
    assert package.hosted_model_used_by_jason is False
    assert package.hosted_model_input_tokens == 0
    assert package.hosted_model_output_tokens == 0
    assert package.hosted_model_cost_usd == "0"
    assert len(package.package_sha256) == 64
    drmm = next(item for item in package.observations if item.provider_id == "datto_rmm")
    assert drmm.freshness is FreshnessClass.REALTIME


def test_failed_provider_result_cannot_enter_reasoning_package() -> None:
    failed = OrchestrationResult(
        execution_id="exec-failed",
        correlation_id="corr-ticket-12345",
        capability_name="service.ticket.read",
        status=OrchestrationStatus.FAILED,
        stage=ExecutionStage.FAILED,
        reason_codes=("capability_invocation_failed",),
        resolution=None,
        provider_id="autotask",
        error_code="PROVIDER_HTTP_STATUS_500",
    )

    with pytest.raises(CrossProviderEvidenceError, match="failed or denied"):
        build_evidence_package(
            correlation_id="corr-ticket-12345",
            principal_id="person-al",
            organization_id="aot",
            client_id="aot",
            results=(failed,),
            freshness_by_capability={"service.ticket.read": FreshnessClass.TRANSACTIONAL},
            created_at=NOW,
        )
