from orchestrator.provider_documentation_source_catalog import (
    DATTO_RMM_OPENAPI_SOURCE,
    datto_rmm_openapi_source,
    register_provider_documentation_sources,
)
from orchestrator.provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    DocumentationSourceApproval,
    DocumentationSourceLifecycle,
    GovernedDocumentationSourceResolver,
    ProviderDocumentationSourceRegistry,
)


def test_datto_openapi_source_is_governed_and_provider_bound():
    source = datto_rmm_openapi_source()

    assert source.source_id == DATTO_RMM_OPENAPI_SOURCE
    assert source.provider_id == "datto_rmm"
    assert source.retrieval_method is DocumentationRetrievalMethod.OPENAPI
    assert source.lifecycle_status is DocumentationSourceLifecycle.AVAILABLE
    assert source.approval_status is DocumentationSourceApproval.APPROVED
    assert source.technology_steward == "technology-steward"
    assert source.allowed_resource_authorities == ("managed_endpoint",)


def test_datto_openapi_source_uses_vendor_authoritative_documentation():
    source = datto_rmm_openapi_source()

    assert (
        source.locator
        == "https://vidal-api.centrastage.net/api/v3/api-docs/Datto-RMM"
    )
    assert (
        source.metadata["vendor_api_help"]
        == "https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm"
    )
    assert source.metadata["api_version"] == "v2"
    assert source.content_type == "application/json"
    assert source.metadata["documentation_kind"] == "openapi-3.0"
    assert source.metadata["vendor"] == "Kaseya"


def test_registered_datto_source_resolves_from_existing_symbolic_name():
    registry = ProviderDocumentationSourceRegistry()
    register_provider_documentation_sources(registry)

    resolved = GovernedDocumentationSourceResolver(
        registry=registry,
    ).resolve(
        provider_id="datto_rmm",
        documentation_name="Datto RMM API documentation",
        resource_authority="managed_endpoint",
    )

    assert resolved.source_id == DATTO_RMM_OPENAPI_SOURCE


def test_catalog_registration_does_not_store_credentials():
    source = datto_rmm_openapi_source().as_context()

    serialized = repr(source).casefold()

    for forbidden in (
        "api_secret",
        "access_token",
        "refresh_token",
        "password",
        "credential_value",
    ):
        assert forbidden not in serialized
