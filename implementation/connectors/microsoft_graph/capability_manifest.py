from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)
from orchestrator.provider_read_capability_catalog import (
    IDENTITY_USER_READ,
    IDENTITY_USER_SEARCH,
    MICROSOFT_GRAPH_PROVIDER,
)


def build_microsoft_graph_manifest() -> IntegrationManifest:
    selectors = (
        SelectorDefinition("email", "Exact Microsoft Entra mail address selector."),
        SelectorDefinition("user_principal_name", "Exact Microsoft Entra user principal name selector."),
        SelectorDefinition("display_name", "Exact Microsoft Entra display name selector; ambiguity is preserved."),
        SelectorDefinition(
            "page_size",
            "Maximum Entra users returned by one exact search; bounded to 1-25.",
        ),
        SelectorDefinition(
            "resource_id",
            "Durable Microsoft Entra object identifier.",
            verified_identity_required=True,
        ),
    )

    return IntegrationManifest(
        integration_id="microsoft_graph_directory",
        display_name="Microsoft Entra Directory",
        manifest_version="1.0",
        provider_id=MICROSOFT_GRAPH_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="identity_user",
                description=(
                    "Microsoft Entra user records in the requester's already-bound and "
                    "validated Microsoft tenant."
                ),
                selectors=selectors,
                operations=(
                    IntegrationOperation(
                        operation_id="identity.user.search",
                        kind=OperationKind.SEARCH,
                        capability_name=IDENTITY_USER_SEARCH,
                        description="Search Microsoft Entra users by one exact bounded selector.",
                        read_only=True,
                        selector_names=(
                            "email",
                            "user_principal_name",
                            "display_name",
                            "page_size",
                        ),
                        collection_supported=True,
                    ),
                    IntegrationOperation(
                        operation_id="identity.user.read",
                        kind=OperationKind.READ,
                        capability_name=IDENTITY_USER_READ,
                        description="Read one Microsoft Entra user by verified object identifier.",
                        read_only=True,
                        selector_names=("resource_id",),
                    ),
                ),
                observations=(
                    ResourceObservation(
                        "identity",
                        "Object id, display name, mail, and user principal name.",
                    ),
                    ResourceObservation(
                        "account_state",
                        "Microsoft Entra account-enabled state.",
                    ),
                ),
                relationships=(),
            ),
        ),
        metadata={
            "mode": "read_only",
            "credential_surface": "internal_openbao_only",
            "tenant_selection": "trusted_microsoft_identity_binding_only",
            "permission_profile": "directory-read",
        },
    )
