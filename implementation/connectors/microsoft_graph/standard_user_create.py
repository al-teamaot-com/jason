"""Source-only standard Microsoft Entra cloud-user creation via governed plan.

This module is not registered by the production runtime. It requires a trusted,
verified AOT client/onboarding authority, an existing sealed initial credential,
a separately scoped Graph User.Create token and independent directory readback.
It never mints admin roles, group permissions or licenses.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorResult, HttpTransport,
)
from orchestrator.connector_invoker import ProviderPreparedExecution


CAPABILITY = "identity.user.create"
GRAPH_USER_URL = "https://graph.microsoft.com/v1.0/users"
PROVISIONING_PROFILE = "user-create"
SOURCE_AUTHORITY = "entra_cloud"
PROFILE_ENV = "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE"
PROFILE_VALUE = "cloud-user-v1"

_UPN_LOCAL = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_MAIL_NICKNAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_REQUEST_REFERENCE = re.compile(r"[A-Za-z0-9_.:-]{5,120}\Z")


def _enabled() -> bool:
    import os
    return os.getenv(PROFILE_ENV, "").strip().casefold() == PROFILE_VALUE


def _text(value: Any, field: str, *, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise ValueError(f"ENTRA_{field}_INVALID")
    normalized = value.strip()
    if (not normalized or len(normalized) > maximum
            or any(ord(ch) < 32 for ch in normalized)):
        raise ValueError(f"ENTRA_{field}_INVALID")
    return normalized


@dataclass(frozen=True, slots=True)
class TrustedCloudUserScope:
    client_id: str
    tenant_id: str
    managed_domains: frozenset[str]
    source_authority: str


class TrustedOnboardingAuthority(Protocol):
    def require_approved_request(
        self, *, context: ConnectorContext, request_id: str,
    ) -> TrustedCloudUserScope: ...


@dataclass(frozen=True, slots=True)
class SealedInitialPassword:
    reference: str
    plaintext: str = field(repr=False)


class InitialCredentialReader(Protocol):
    """Read already-issued sealed credential, with no generation side effects."""
    def read_for_onboarding(
        self, *, client_id: str, request_id: str, upn: str,
    ) -> SealedInitialPassword: ...


class GraphDirectoryReader(Protocol):
    def search_users(
        self, *, microsoft_tenant_id: str, selector: str,
        value: str, maximum_records: int = 10,
    ) -> tuple[Mapping[str, Any], ...]: ...

    def read_user(
        self, *, microsoft_tenant_id: str, microsoft_object_id: str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ScopedGraphCreateToken:
    tenant_id: str
    profile: str
    access_token: str = field(repr=False)


class ScopedGraphCreateTokens(Protocol):
    def token_for_tenant(
        self, *, tenant_id: str, profile: str,
    ) -> ScopedGraphCreateToken: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphCreateUserWriter:
    """Fixed Graph v1.0 POST only; never accepts a caller-supplied URL/path."""
    tokens: ScopedGraphCreateTokens
    transport: HttpTransport

    def create_user(
        self, *, tenant_id: str, payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        token = self.tokens.token_for_tenant(
            tenant_id=tenant_id, profile=PROVISIONING_PROFILE,
        )
        if (not isinstance(token, ScopedGraphCreateToken)
                or token.tenant_id != tenant_id
                or token.profile != PROVISIONING_PROFILE
                or not isinstance(token.access_token, str)
                or not token.access_token.strip()):
            raise ConnectorAuthorizationError("ENTRA_CREATE_TOKEN_SCOPE_MISMATCH")
        response = self.transport.request(
            method="POST", url=GRAPH_USER_URL,
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Content-Type": "application/json",
            },
            params=None, json=payload, timeout_seconds=20.0,
        )
        if not isinstance(response, Mapping):
            raise RuntimeError("ENTRA_CREATE_RESPONSE_INVALID")
        return response


@dataclass(frozen=True, slots=True)
class _PreparedUser:
    context: ConnectorContext
    scope: TrustedCloudUserScope
    request_id: str
    provider_payload: Mapping[str, Any] = field(repr=False)
    credential_reference: str
    normalized_upn: str


@dataclass(frozen=True, slots=True)
class MicrosoftGraphStandardUserCreateConnector:
    reader: GraphDirectoryReader
    writer: MicrosoftGraphCreateUserWriter
    authority: TrustedOnboardingAuthority
    credentials: InitialCredentialReader
    audit: AuditSink

    provider_name = "microsoft_graph"
    capabilities = frozenset({CAPABILITY})

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        raise ConnectorAuthorizationError("ENTRA_GOVERNED_EXECUTION_PLAN_REQUIRED")

    def _validate(
        self, request: ConnectorRequest,
    ) -> tuple[TrustedCloudUserScope, str, str, dict[str, Any]]:
        if not _enabled():
            raise PermissionError("ENTRA_STANDARD_CREATE_DISABLED")
        context = request.context
        if (context.capability != CAPABILITY
                or context.mode != "execute"
                or context.organization_id != "aot"
                or not context.client_id):
            raise ConnectorAuthorizationError("ENTRA_EXACT_CLIENT_EXECUTE_REQUIRED")
        args = request.arguments
        allowed = {
            "onboarding_request_id", "user_principal_name", "display_name",
            "mail_nickname", "given_name", "surname", "usage_location",
        }
        if set(args) - allowed or not all(k in args for k in (
            "onboarding_request_id", "user_principal_name", "display_name",
            "mail_nickname",
        )):
            raise ValueError("ENTRA_STANDARD_USER_FIELDS_ONLY")
        request_id = _text(
            args["onboarding_request_id"], "ONBOARDING_REQUEST_ID",
        )
        if not _REQUEST_REFERENCE.fullmatch(request_id):
            raise ValueError("ENTRA_ONBOARDING_REFERENCE_INVALID")
        scope = self.authority.require_approved_request(
            context=context, request_id=request_id,
        )
        if (not isinstance(scope, TrustedCloudUserScope)
                or scope.client_id != context.client_id
                or not scope.tenant_id.strip()
                or scope.source_authority != SOURCE_AUTHORITY):
            raise ConnectorAuthorizationError("ENTRA_CLOUD_SOURCE_AUTHORITY_REQUIRED")
        upn = _text(args["user_principal_name"], "UPN").casefold()
        if upn.count("@") != 1:
            raise ValueError("ENTRA_UPN_INVALID")
        local, domain = upn.split("@")
        if (not _UPN_LOCAL.fullmatch(local)
                or local.endswith(".")
                or ".." in local
                or not domain
                or domain not in {d.casefold() for d in scope.managed_domains}):
            raise ConnectorAuthorizationError("ENTRA_UPN_DOMAIN_NOT_APPROVED")
        if local in {"admin", "administrator", "globaladmin", "breakglass"}:
            raise ConnectorAuthorizationError("ENTRA_PRIVILEGED_NAME_NOT_STANDARD")
        alias = _text(args["mail_nickname"], "MAIL_NICKNAME").casefold()
        if not _MAIL_NICKNAME.fullmatch(alias) or alias.endswith("."):
            raise ValueError("ENTRA_MAIL_NICKNAME_INVALID")
        payload = {
            "accountEnabled": False,
            "displayName": _text(args["display_name"], "DISPLAY_NAME"),
            "mailNickname": alias,
            "userPrincipalName": upn,
        }
        for argument, graph_field in (
            ("given_name", "givenName"),
            ("surname", "surname"),
        ):
            if argument in args:
                payload[graph_field] = _text(args[argument], graph_field)
        if "usage_location" in args:
            usage = _text(args["usage_location"], "USAGE_LOCATION", maximum=2)
            if len(usage) != 2 or not usage.isascii() or not usage.isalpha():
                raise ValueError("ENTRA_USAGE_LOCATION_INVALID")
            payload["usageLocation"] = usage.upper()
        return scope, request_id, upn, payload

    def _assert_absent(self, *, tenant_id: str, upn: str) -> None:
        matches = self.reader.search_users(
            microsoft_tenant_id=tenant_id,
            selector="user_principal_name", value=upn, maximum_records=10,
        )
        if not isinstance(matches, tuple) or len(matches) > 10:
            raise ConnectorAuthorizationError("ENTRA_DUPLICATE_SEARCH_INCOMPLETE")
        if matches:
            raise ConnectorAuthorizationError("ENTRA_USER_ALREADY_EXISTS")

    def prepare_governed_execution(
        self, request: ConnectorRequest,
    ) -> ProviderPreparedExecution:
        scope, request_id, upn, payload = self._validate(request)
        self._assert_absent(tenant_id=scope.tenant_id, upn=upn)
        sealed = self.credentials.read_for_onboarding(
            client_id=scope.client_id, request_id=request_id, upn=upn,
        )
        if (not isinstance(sealed, SealedInitialPassword)
                or not sealed.reference.strip()
                or not isinstance(sealed.plaintext, str)
                or len(sealed.plaintext) < 16):
            raise PermissionError("ENTRA_SEALED_CREDENTIAL_UNAVAILABLE")
        actual_payload = {
            **payload,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": sealed.plaintext,
            },
        }
        # The credential is committed by a one-way digest and held only in
        # ephemeral opaque provider state, not the persisted plan/audit.
        planned_payload = {
            **payload,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password_sha256": hashlib.sha256(
                    sealed.plaintext.encode("utf-8")
                ).hexdigest(),
                "sealed_reference": sealed.reference,
            },
        }
        return ProviderPreparedExecution(
            provider_capability=CAPABILITY,
            action_method="POST", resource_type="identity_user",
            resource_identifier=upn,
            normalized_path="/users",
            payload=planned_payload,
            parameters={"tenant_id": scope.tenant_id, "client_id": scope.client_id,
                        "onboarding_request_id": request_id},
            opaque=_PreparedUser(
                context=request.context, scope=scope, request_id=request_id,
                provider_payload=actual_payload,
                credential_reference=sealed.reference,
                normalized_upn=upn,
            ),
        )

    def execute_governed_execution(
        self, prepared: ProviderPreparedExecution,
    ) -> ConnectorResult:
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedUser) or not _enabled():
            raise PermissionError("ENTRA_PREPARED_USER_INVALID_OR_DISABLED")
        # A prepared object is not an authorization token by itself.
        ctx = opaque.context
        if (ctx.capability != CAPABILITY or ctx.mode != "execute"
                or ctx.organization_id != "aot" or not ctx.client_id
                or ctx.client_id != opaque.scope.client_id):
            raise ConnectorAuthorizationError("ENTRA_PREPARED_IDENTITY_SCOPE_INVALID")
        # Reverify existing onboarding authorization independently of the
        # signed execution plan. No client, tenant or source substitution.
        requested_scope = self.authority.require_approved_request(
            context=opaque.context, request_id=opaque.request_id,
        )
        if requested_scope != opaque.scope or opaque.scope.source_authority != SOURCE_AUTHORITY:
            raise ConnectorAuthorizationError("ENTRA_ONBOARDING_AUTHORITY_CHANGED")
        secret = self.credentials.read_for_onboarding(
            client_id=opaque.scope.client_id, request_id=opaque.request_id,
            upn=opaque.normalized_upn,
        )
        if (not isinstance(secret, SealedInitialPassword)
                or secret.reference != opaque.credential_reference
                or opaque.provider_payload["passwordProfile"]["password"]
                   != secret.plaintext):
            raise ConnectorAuthorizationError("ENTRA_CREDENTIAL_COMMITMENT_CHANGED")
        expected_plan = {
            **{k: v for k, v in opaque.provider_payload.items()
               if k != "passwordProfile"},
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password_sha256": hashlib.sha256(
                    secret.plaintext.encode("utf-8")
                ).hexdigest(),
                "sealed_reference": secret.reference,
            },
        }
        if (prepared.provider_capability != CAPABILITY
                or prepared.action_method != "POST"
                or prepared.resource_type != "identity_user"
                or prepared.resource_identifier != opaque.normalized_upn
                or prepared.normalized_path != "/users"
                or dict(prepared.payload) != expected_plan
                or dict(prepared.parameters) != {
                    "tenant_id": opaque.scope.tenant_id,
                    "client_id": opaque.scope.client_id,
                    "onboarding_request_id": opaque.request_id,
                }):
            raise ConnectorAuthorizationError("ENTRA_EXECUTION_PLAN_MISMATCH")
        self._assert_absent(
            tenant_id=opaque.scope.tenant_id, upn=opaque.normalized_upn,
        )
        self.audit.record("connector.mutation.requested", opaque.context, {
            "provider": self.provider_name,
            "capability": CAPABILITY,
            "request_id": opaque.request_id,
        })
        created = self.writer.create_user(
            tenant_id=opaque.scope.tenant_id,
            payload=opaque.provider_payload,
        )
        created_id = str(created.get("id") or "").strip()
        if not created_id:
            raise RuntimeError("ENTRA_CREATE_ID_MISSING")
        observed = self.reader.read_user(
            microsoft_tenant_id=opaque.scope.tenant_id,
            microsoft_object_id=created_id,
        )
        if (str(observed.get("id") or "").casefold() != created_id.casefold()
                or str(observed.get("userPrincipalName") or "").casefold()
                   != opaque.normalized_upn
                or observed.get("displayName")
                   != opaque.provider_payload["displayName"]
                or observed.get("accountEnabled") is not False):
            self.audit.record("connector.mutation.verification_failed", opaque.context, {
                "provider": self.provider_name,
                "request_id": opaque.request_id,
            })
            raise RuntimeError("ENTRA_CREATE_READBACK_FAILED")
        self.audit.record("connector.mutation.verified", opaque.context, {
            "provider": self.provider_name,
            "request_id": opaque.request_id,
        })
        return ConnectorResult(
            capability=CAPABILITY, provider=self.provider_name,
            data={
                "object_id": created_id,
                "user_principal_name": opaque.normalized_upn,
                "account_enabled": False,
                "credential_delivery": "separate_secure_workflow_required",
                "jasonVerification": {"readbackVerified": True},
            },
            evidence_ids=(f"microsoft_graph:user:{created_id}",),
        )
