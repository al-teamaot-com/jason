from __future__ import annotations

from .provider_documentation_source_registry import (
    DocumentationRetrievalMethod,
    DocumentationSourceApproval,
    DocumentationSourceLifecycle,
    ProviderDocumentationSourceDefinition,
    ProviderDocumentationSourceRegistry,
)


DATTO_RMM_OPENAPI_SOURCE = "datto-rmm-openapi-v2"


def datto_rmm_openapi_source() -> ProviderDocumentationSourceDefinition:
    return ProviderDocumentationSourceDefinition(
        source_id=DATTO_RMM_OPENAPI_SOURCE,
        provider_id="datto_rmm",
        display_name="Datto RMM API documentation",
        authority="Kaseya Datto RMM authoritative API v2 Swagger documentation",
        retrieval_method=DocumentationRetrievalMethod.OPENAPI,
        locator="https://vidal-api.centrastage.net/api/v3/api-docs/Datto-RMM",
        content_type="application/json",
        lifecycle_status=DocumentationSourceLifecycle.AVAILABLE,
        approval_status=DocumentationSourceApproval.APPROVED,
        technology_steward="technology-steward",
        business_justification=(
            "Datto RMM is the approved managed-endpoint authority. "
            "Its vendor-published API v2 Swagger documentation is the authoritative "
            "documentation source for governed discovery of existing endpoint API capabilities."
        ),
        review_interval_days=90,
        retirement_criteria=(
            "Kaseya replaces or retires this Datto RMM API documentation source.",
            "Datto RMM API v2 is superseded by a newer authoritative API version.",
            "Datto RMM is no longer the approved managed-endpoint authority.",
        ),
        allowed_resource_authorities=("managed_endpoint",),
        metadata={
            "aliases": (
                "Datto RMM API documentation|"
                "Datto RMM Swagger documentation|"
                "Datto RMM API v2"
            ),
            "vendor": "Kaseya",
            "api_version": "v2",
            "documentation_kind": "openapi-3.0",
            "vendor_api_help": (
                "https://rmm.datto.com/help/en/Content/2SETUP/APIv2.htm"
            ),
        },
    )


def register_provider_documentation_sources(
    registry: ProviderDocumentationSourceRegistry,
) -> None:
    registry.register(datto_rmm_openapi_source())
