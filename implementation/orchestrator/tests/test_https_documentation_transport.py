import pytest

from orchestrator.https_documentation_transport import (
    GovernedHttpsDocumentationTransport,
)
from orchestrator.provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    DocumentationSourceApproval,
    DocumentationSourceLifecycle,
    ProviderDocumentationSourceDefinition,
)


def source(locator="https://example.invalid/openapi"):
    return ProviderDocumentationSourceDefinition(
        source_id="example-openapi",
        provider_id="example_provider",
        display_name="Example Provider API documentation",
        authority="Example Provider authoritative API documentation",
        retrieval_method=DocumentationRetrievalMethod.OPENAPI,
        locator=locator,
        content_type="application/json",
        lifecycle_status=DocumentationSourceLifecycle.AVAILABLE,
        approval_status=DocumentationSourceApproval.APPROVED,
        technology_steward="technology-steward",
        business_justification="test",
        review_interval_days=90,
        retirement_criteria=("retire when superseded",),
    )


def test_transport_rejects_non_https_locator():
    transport = GovernedHttpsDocumentationTransport()

    with pytest.raises(PermissionError, match="HTTPS locator"):
        transport.fetch(
            source=source("http://example.invalid/openapi")
        )


def test_transport_rejects_unsupported_retrieval_method():
    record = ProviderDocumentationSourceDefinition(
        source_id="local",
        provider_id="example_provider",
        display_name="Local documentation",
        authority="local",
        retrieval_method=DocumentationRetrievalMethod.LOCAL_ARTIFACT,
        locator="https://example.invalid/local",
        content_type="application/json",
        lifecycle_status=DocumentationSourceLifecycle.AVAILABLE,
        approval_status=DocumentationSourceApproval.APPROVED,
        technology_steward="technology-steward",
        business_justification="test",
        review_interval_days=90,
        retirement_criteria=("retire when superseded",),
    )

    with pytest.raises(PermissionError):
        GovernedHttpsDocumentationTransport().fetch(source=record)


def test_transport_rejects_invalid_timeout():
    with pytest.raises(ValueError):
        GovernedHttpsDocumentationTransport(timeout_seconds=0)


def test_transport_rejects_invalid_size_limit():
    with pytest.raises(ValueError):
        GovernedHttpsDocumentationTransport(max_response_bytes=0)
