import pytest

from orchestrator.provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    DocumentationSourceApproval,
    DocumentationSourceLifecycle,
    GovernedDocumentationSourceResolver,
    ProviderDocumentationSourceDefinition,
    ProviderDocumentationSourceRegistry,
)


def source(
    *,
    source_id="example-api",
    provider_id="example_provider",
    display_name="Example Provider API documentation",
    approval=DocumentationSourceApproval.APPROVED,
    lifecycle=DocumentationSourceLifecycle.AVAILABLE,
):
    return ProviderDocumentationSourceDefinition(
        source_id=source_id,
        provider_id=provider_id,
        display_name=display_name,
        authority="Example Provider authoritative API documentation",
        retrieval_method=DocumentationRetrievalMethod.OPENAPI,
        locator="registry://example-provider/openapi",
        content_type="application/openapi+json",
        lifecycle_status=lifecycle,
        approval_status=approval,
        technology_steward="technology-steward",
        business_justification=(
            "Authoritative provider documentation is required for governed "
            "capability and evidence discovery."
        ),
        review_interval_days=90,
        retirement_criteria=(
            "Provider retires this documentation source.",
            "A newer authoritative source supersedes it.",
        ),
        allowed_resource_authorities=("managed_endpoint",),
        metadata={
            "aliases": "Example Provider API documentation|Example API docs",
        },
    )


def test_registry_resolves_approved_provider_documentation_source():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(source())

    resolved = GovernedDocumentationSourceResolver(
        registry=registry,
    ).resolve(
        provider_id="example_provider",
        documentation_name="Example Provider API documentation",
        resource_authority="managed_endpoint",
    )

    assert resolved.source_id == "example-api"
    assert resolved.retrieval_method is DocumentationRetrievalMethod.OPENAPI


def test_registry_does_not_return_blocked_source():
    registry = ProviderDocumentationSourceRegistry()

    with pytest.raises(ValueError):
        registry.register(
            source(
                approval=DocumentationSourceApproval.BLOCKED,
            )
        )


def test_registry_does_not_return_retired_source():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(
        source(
            lifecycle=DocumentationSourceLifecycle.RETIRED,
        )
    )

    with pytest.raises(LookupError):
        GovernedDocumentationSourceResolver(
            registry=registry,
        ).resolve(
            provider_id="example_provider",
            documentation_name="Example Provider API documentation",
        )


def test_registry_rejects_duplicate_source_identifier():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(source())

    with pytest.raises(ValueError):
        registry.register(source())


def test_resolution_rejects_wrong_resource_authority():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(source())

    with pytest.raises(LookupError):
        GovernedDocumentationSourceResolver(
            registry=registry,
        ).resolve(
            provider_id="example_provider",
            documentation_name="Example Provider API documentation",
            resource_authority="different_authority",
        )


def test_resolution_fails_closed_when_ambiguous():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(source(source_id="source-a"))
    registry.register(source(source_id="source-b"))

    with pytest.raises(LookupError, match="ambiguous"):
        GovernedDocumentationSourceResolver(
            registry=registry,
        ).resolve(
            provider_id="example_provider",
            documentation_name="Example Provider API documentation",
        )


def test_registry_definition_contains_no_secret_material_contract():
    record = source().as_context()

    forbidden = {
        "password",
        "secret",
        "token",
        "api_key",
        "credential",
        "credentials",
    }

    assert forbidden.isdisjoint(record)
