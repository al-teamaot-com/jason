import pytest

from orchestrator.openapi_documentation_source_adapter import (
    GovernedOpenApiDocumentationSourceAdapter,
    StaticDocumentationContentTransport,
)
from orchestrator.provider_documentation_review import (
    ProviderDocumentationReviewTarget,
)
from orchestrator.provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    DocumentationSourceApproval,
    DocumentationSourceLifecycle,
    GovernedDocumentationSourceResolver,
    ProviderDocumentationSourceDefinition,
    ProviderDocumentationSourceRegistry,
)


def build_source(
    *,
    retrieval_method=DocumentationRetrievalMethod.OPENAPI,
    locator="registry://example/openapi",
):
    return ProviderDocumentationSourceDefinition(
        source_id="example-openapi",
        provider_id="example_provider",
        display_name="Example Provider API documentation",
        authority="Example Provider authoritative OpenAPI documentation",
        retrieval_method=retrieval_method,
        locator=locator,
        content_type="application/openapi+json",
        lifecycle_status=DocumentationSourceLifecycle.AVAILABLE,
        approval_status=DocumentationSourceApproval.APPROVED,
        technology_steward="technology-steward",
        business_justification="Governed provider API documentation review.",
        review_interval_days=90,
        retirement_criteria=("Superseded by newer authoritative documentation.",),
        allowed_resource_authorities=("managed_endpoint",),
        metadata={
            "aliases": "Example Provider API documentation",
        },
    )


def build_target():
    return ProviderDocumentationReviewTarget(
        provider_id="example_provider",
        documentation_source="Example Provider API documentation",
        unsupported_facts=("special governed fact",),
        resource_authority="managed_endpoint",
        connector_id="example_connector",
    )


def build_adapter(*, source=None, payload=b'{"openapi":"3.0.0"}'):
    registry = ProviderDocumentationSourceRegistry()
    registry.register(source or build_source())

    return GovernedOpenApiDocumentationSourceAdapter(
        resolver=GovernedDocumentationSourceResolver(registry=registry),
        transport=StaticDocumentationContentTransport(
            documents={"registry://example/openapi": payload}
        ),
    )


def test_adapter_returns_bounded_source_record_with_content_hash():
    records = build_adapter().read(target=build_target())

    assert len(records) == 1
    record = records[0]

    assert record.provider_id == "example_provider"
    assert record.documentation_source == "Example Provider API documentation"
    assert record.content == '{"openapi":"3.0.0"}'
    assert record.source_reference.startswith("example-openapi:sha256:")


def test_adapter_rejects_non_openapi_source():
    adapter = build_adapter(
        source=build_source(
            retrieval_method=DocumentationRetrievalMethod.HTTPS,
        )
    )

    with pytest.raises(PermissionError):
        adapter.read(target=build_target())


def test_adapter_rejects_empty_document():
    adapter = build_adapter(payload=b"")

    with pytest.raises(ValueError, match="empty"):
        adapter.read(target=build_target())


def test_adapter_rejects_non_utf8_document():
    adapter = build_adapter(payload=b"\xff\xfe")

    with pytest.raises(ValueError, match="UTF-8"):
        adapter.read(target=build_target())


def test_adapter_enforces_governed_size_limit():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(build_source())

    adapter = GovernedOpenApiDocumentationSourceAdapter(
        resolver=GovernedDocumentationSourceResolver(registry=registry),
        transport=StaticDocumentationContentTransport(
            documents={"registry://example/openapi": b"12345"}
        ),
        max_document_bytes=4,
    )

    with pytest.raises(ValueError, match="size limit"):
        adapter.read(target=build_target())


def test_adapter_fails_closed_when_documentation_name_is_not_registered():
    registry = ProviderDocumentationSourceRegistry()
    registry.register(build_source())

    adapter = GovernedOpenApiDocumentationSourceAdapter(
        resolver=GovernedDocumentationSourceResolver(registry=registry),
        transport=StaticDocumentationContentTransport(
            documents={"registry://example/openapi": b"{}"}
        ),
    )

    target = ProviderDocumentationReviewTarget(
        provider_id="example_provider",
        documentation_source="Different documentation",
        unsupported_facts=("special governed fact",),
        resource_authority="managed_endpoint",
    )

    with pytest.raises(LookupError):
        adapter.read(target=target)
