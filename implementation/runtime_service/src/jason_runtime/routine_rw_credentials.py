"""Credential-backed adapters for fixed, client-scoped routine provisioning.

No secret generation, credential provisioning, or direct Graph mutation is
performed here. Write credentials use dedicated OpenBao AppRoles, separate
from the existing read-only connectors.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from connectors.core.contracts import ConnectorContext, ConnectorAuthorizationError
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.standard_user_create import (
    PROVISIONING_PROFILE, ScopedGraphCreateToken, SealedInitialPassword,
)
from connectors.microsoft_graph.token import MicrosoftApplicationTokenProvider
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository


@dataclass(frozen=True, slots=True)
class GovernedGraphUserCreateTokens:
    boundaries: ClientBoundaryRepository
    provider: MicrosoftApplicationTokenProvider

    def token_for_tenant(
        self, *, tenant_id: str, profile: str,
    ) -> ScopedGraphCreateToken:
        if profile != PROVISIONING_PROFILE or not tenant_id.strip():
            raise ConnectorAuthorizationError("ENTRA_CREATE_PROFILE_NOT_APPROVED")
        boundary = self.boundaries.find_active_for_external_tenant(
            provider="microsoft_graph_user_create",
            external_tenant_id=tenant_id.strip(),
        )
        if (boundary is None or boundary.status != BoundaryStatus.VALIDATED
                or boundary.profile != PROVISIONING_PROFILE
                or boundary.external_tenant_id.casefold() != tenant_id.casefold()):
            raise ConnectorAuthorizationError("ENTRA_USER_CREATE_BOUNDARY_NOT_VALIDATED")
        token = self.provider.acquire_for_client(
            client_id=boundary.client_id,
            correlation_id=f"identity-user-create:{boundary.client_id}",
        )
        if (token.tenant_id.casefold() != boundary.external_tenant_id.casefold()
                or token.application_id.casefold() != boundary.application_id.casefold()
                or not token.access_token.strip()):
            raise ConnectorAuthorizationError("ENTRA_USER_CREATE_TOKEN_BOUNDARY_MISMATCH")
        return ScopedGraphCreateToken(
            tenant_id=token.tenant_id, profile=PROVISIONING_PROFILE,
            access_token=token.access_token,
        )


@dataclass(frozen=True, slots=True)
class OpenBaoOnboardingPasswordReader:
    """Read one exact pre-provisioned password, isolated by hashed request path.

    Provider secret:
      secret/data/connectors/microsoft-graph/onboarding-passwords/<sha256>
    Path hash = sha256("client-id|request-id|canonical-upn").
    Required KV v2 attributes:
      client_id, onboarding_request_id, user_principal_name,
      credential_reference, password
    """

    openbao_url: str
    role_id_path: Path
    secret_id_path: Path

    def read_for_onboarding(
        self, *, client_id: str, request_id: str, upn: str,
    ) -> SealedInitialPassword:
        if (not client_id.strip() or not request_id.strip()
                or not upn.strip() or upn.casefold() != upn):
            raise ConnectorAuthorizationError("ENTRA_ONBOARDING_CREDENTIAL_SCOPE_INVALID")
        digest = hashlib.sha256(
            f"{client_id}|{request_id}|{upn}".encode("utf-8")
        ).hexdigest()
        logical_name = "microsoft_graph.onboarding_initial_password"
        resolver = OpenBaoSecretResolver(
            base_url=self.openbao_url,
            role_id_path=self.role_id_path,
            secret_id_path=self.secret_id_path,
            mappings={
                logical_name:
                    "secret/data/connectors/microsoft-graph/"
                    f"onboarding-passwords/{digest}"
            },
            allowed_fields={
                logical_name: frozenset({
                    "client_id", "onboarding_request_id",
                    "user_principal_name", "credential_reference", "password",
                })
            },
        )
        context = ConnectorContext(
            correlation_id=f"onboarding-password:{digest}",
            principal_id="microsoft-graph-provisioning-secret-reader",
            organization_id="aot", client_id=client_id,
            capability="identity.user.create", mode="execute",
        )
        values = resolver.resolve(logical_name, context)
        if (values["client_id"] != client_id
                or values["onboarding_request_id"] != request_id
                or values["user_principal_name"].casefold() != upn
                or not values["credential_reference"].strip()
                or len(values["password"]) < 16):
            raise ConnectorAuthorizationError(
                "ENTRA_SEALED_ONBOARDING_CREDENTIAL_MISMATCH"
            )
        return SealedInitialPassword(
            reference=values["credential_reference"],
            plaintext=values["password"],
        )
