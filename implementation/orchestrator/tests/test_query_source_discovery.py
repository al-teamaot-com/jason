from datetime import (
    datetime,
    timezone,
)

import pytest

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)

from orchestrator.query_source_discovery import (
    GovernedQuerySourceDiscovery,
    QuerySourceDiscoveryError,
)
from orchestrator.semantic_query_planning import (
    SemanticQuerySource,
)


NOW = datetime(
    2026,
    1,
    1,
    tzinfo=timezone.utc,
)


def capability(
    name,
    *,
    resource_type,
    facts,
    collection=True,
):
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=name,
        lifecycle_status=(
            CapabilityLifecycle.ACTIVE
        ),
        business_purpose=(
            "Synthetic governed resource read."
        ),
        owner_service="test",
        architectural_capability_ids=(
            frozenset({"JAC-005"})
        ),
        risk_level=CapabilityRisk.LOW,
        data_classifications=(
            frozenset({"internal"})
        ),
        permitted_execution_modes=(
            frozenset({"deterministic"})
        ),
        input_schema_reference="schema://test/input",
        output_schema_reference="schema://test/output",
        invoking_roles=(
            frozenset({"orchestrator"})
        ),
        approval=CapabilityApproval(
            required=False
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("result",),
            verification_requirements=("verified",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=(
            IdempotencyBehavior.IDEMPOTENT
        ),
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="fail closed",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="test",
            business_justification="test",
            review_interval_days=90,
            retirement_criteria=("test",),
            authoritative_change_sources=("test",),
        ),
        created_at=NOW,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_type,
            "operation": "search",
            "selector_keys": "resource_id,name",
            "selector_required": (
                "false"
                if collection
                else "true"
            ),
            **(
                {
                    "collection_scope": "authorized"
                }
                if collection
                else {}
            ),
            "canonical_facts": ",".join(
                facts
            ),
        },
    )


def provider(
    provider_id,
    capabilities,
):
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=provider_id,
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset(
            {"deterministic"}
        ),
        capabilities=frozenset(
            capabilities
        ),
        supported_classifications=frozenset(
            {"internal"}
        ),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_requests_per_minute=100,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(
            structured_output=True
        ),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="test",
            business_justification="test",
            review_interval_days=90,
            last_reviewed_at=NOW,
            retirement_criteria=("test",),
            vendor_change_sources=("test",),
        ),
        created_at=NOW,
        metadata={},
    )


def discovery(
    capabilities,
    providers,
):
    capability_service = (
        CapabilityRegistryService(
            registry=(
                InMemoryCapabilityRegistry()
            )
        )
    )

    provider_service = (
        ExecutionProviderRegistryService(
            registry=(
                InMemoryExecutionProviderRegistry()
            )
        )
    )

    for item in capabilities:
        capability_service.register(
            item
        )

    for item in providers:
        provider_service.register(
            item
        )

    return GovernedQuerySourceDiscovery(
        capabilities=(
            capability_service
        ),
        providers=(
            provider_service
        ),
    )


def test_discovers_fact_contributions_from_multiple_runtime_providers():
    first = capability(
        "resource.alpha.read",
        resource_type="object",
        facts=("fact_one",),
    )

    second = capability(
        "resource.beta.read",
        resource_type="object",
        facts=("fact_two",),
    )

    service = discovery(
        (
            first,
            second,
        ),
        (
            provider(
                "source-a",
                ("resource.alpha.read",),
            ),
            provider(
                "source-b",
                ("resource.beta.read",),
            ),
        ),
    )

    binding = service.discover(
        SemanticQuerySource(
            alias="objects",
            resource_type="object",
            scope="collection",
            required_facts=(
                "fact_one",
                "fact_two",
            ),
        )
    )

    assert binding.covered_facts == (
        "fact_one",
        "fact_two",
    )

    assert {
        item.provider_id
        for item in binding.contributions
    } == {
        "source-a",
        "source-b",
    }


def test_new_provider_requires_no_discovery_code_change():
    cap = capability(
        "resource.generic.read",
        resource_type="object",
        facts=("fact_one",),
    )

    service = discovery(
        (cap,),
        (
            provider(
                "source-a",
                ("resource.generic.read",),
            ),
            provider(
                "source-b",
                ("resource.generic.read",),
            ),
            provider(
                "source-c",
                ("resource.generic.read",),
            ),
        ),
    )

    binding = service.discover(
        SemanticQuerySource(
            alias="objects",
            resource_type="object",
            scope="collection",
            required_facts=("fact_one",),
        )
    )

    assert {
        item.provider_id
        for item in binding.contributions
    } == {
        "source-a",
        "source-b",
        "source-c",
    }


def test_missing_fact_coverage_fails_closed():
    cap = capability(
        "resource.generic.read",
        resource_type="object",
        facts=("fact_one",),
    )

    service = discovery(
        (cap,),
        (
            provider(
                "source-a",
                ("resource.generic.read",),
            ),
        ),
    )

    with pytest.raises(
        QuerySourceDiscoveryError,
        match="covers required canonical facts",
    ):
        service.discover(
            SemanticQuerySource(
                alias="objects",
                resource_type="object",
                scope="collection",
                required_facts=(
                    "fact_one",
                    "fact_missing",
                ),
            )
        )


def test_collection_scope_requires_structural_collection_contract():
    cap = capability(
        "resource.single.read",
        resource_type="object",
        facts=("fact_one",),
        collection=False,
    )

    service = discovery(
        (cap,),
        (
            provider(
                "source-a",
                ("resource.single.read",),
            ),
        ),
    )

    with pytest.raises(
        QuerySourceDiscoveryError
    ):
        service.discover(
            SemanticQuerySource(
                alias="objects",
                resource_type="object",
                scope="collection",
                required_facts=("fact_one",),
            )
        )


def test_runtime_universe_is_derived_from_registered_capabilities_and_providers():
    from orchestrator.query_source_discovery import (
        RuntimeSemanticQueryUniverseBuilder,
    )

    cap_one = capability(
        "resource.universe.one",
        resource_type="object",
        facts=("fact_one",),
    )

    cap_two = capability(
        "resource.universe.two",
        resource_type="object",
        facts=("fact_two",),
    )

    service = discovery(
        (
            cap_one,
            cap_two,
        ),
        (
            provider(
                "source-one",
                ("resource.universe.one",),
            ),
            provider(
                "source-two",
                ("resource.universe.two",),
            ),
        ),
    )

    universe = (
        RuntimeSemanticQueryUniverseBuilder(
            capabilities=service.capabilities,
            providers=service.providers,
        ).build()
    )

    assert len(
        universe.resources
    ) == 1

    resource = universe.resources[0]

    assert resource.resource_type == "object"

    assert {
        fact.name
        for fact in resource.facts
    } == {
        "fact_one",
        "fact_two",
    }

    assert (
        resource.collection_supported
        is True
    )


def test_universe_does_not_expose_capability_without_available_provider():
    from orchestrator.query_source_discovery import (
        RuntimeSemanticQueryUniverseBuilder,
        QuerySourceDiscoveryError,
    )

    cap = capability(
        "resource.unbacked.read",
        resource_type="object",
        facts=("fact_one",),
    )

    service = discovery(
        (cap,),
        (),
    )

    with pytest.raises(
        QuerySourceDiscoveryError,
        match="no governed semantic query resources",
    ):
        RuntimeSemanticQueryUniverseBuilder(
            capabilities=service.capabilities,
            providers=service.providers,
        ).build()
