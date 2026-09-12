from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationMode, OrchestrationRequest
from .information_authorization import (
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
    InformationRemediation,
)
from .information_sensitivity import assess_sensitive_evidence
from .provider_read_capability_catalog import (
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
)
from .service import CapabilityInvoker, InvocationResult


class SourceAuthorizationMode(str, Enum):
    DELEGATED = "delegated"
    IMPERSONATED = "impersonated"
    ACL_MIRRORED = "acl_mirrored"
    JASON_MANAGED = "jason_managed"
    SERVICE_ONLY = "service_only"


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


_SENSITIVE_DOCUMENT_SEARCH_ATTRIBUTE_KEYS = frozenset(
    {
        "content",
        "rendered-content",
        "rendered_content",
        "sections",
    }
)
_DOCUMENT_AUTHORIZATION_RELATIONSHIPS = frozenset(
    {
        "authorized_users",
        "authorized-users",
        "user_resource_accesses",
        "user-resource-accesses",
        "group_resource_accesses",
        "group-resource-accesses",
    }
)


def _decision(
    action: InformationAction,
    *,
    allowed: bool,
    reason_code: str,
    handling_class: InformationHandlingClass,
    remediation: InformationRemediation = InformationRemediation.NONE,
    basis: tuple[str, ...] = (),
) -> InformationAuthorizationDecision:
    return InformationAuthorizationDecision(
        action=action,
        allowed=allowed,
        reason_code=reason_code,
        handling_class=handling_class,
        remediation=remediation,
        policy_ids=("provider-information-authorization-v1",),
        authorization_basis=basis,
    )


def _service_only_envelope(
    *,
    provider_id: str,
    resource_type: str,
    reason_code: str = "SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED",
) -> InformationAuthorizationEnvelope:
    handling = InformationHandlingClass.EXECUTION_ONLY
    return InformationAuthorizationEnvelope(
        handling_class=handling,
        decisions={
            InformationAction.FETCH: _decision(
                InformationAction.FETCH,
                allowed=True,
                reason_code="SERVICE_IDENTITY_FETCH_ALLOWED",
                handling_class=handling,
                basis=(SourceAuthorizationMode.SERVICE_ONLY.value,),
            ),
            InformationAction.USE: _decision(
                InformationAction.USE,
                allowed=False,
                reason_code=reason_code,
                handling_class=handling,
                remediation=InformationRemediation.REQUEST_ACCESS,
                basis=(SourceAuthorizationMode.SERVICE_ONLY.value,),
            ),
            InformationAction.PROCESS: _decision(
                InformationAction.PROCESS,
                allowed=False,
                reason_code=reason_code,
                handling_class=handling,
                remediation=InformationRemediation.REQUEST_ACCESS,
                basis=(SourceAuthorizationMode.SERVICE_ONLY.value,),
            ),
            InformationAction.RELEASE: _decision(
                InformationAction.RELEASE,
                allowed=False,
                reason_code=reason_code,
                handling_class=handling,
                remediation=InformationRemediation.REQUEST_ACCESS,
                basis=(SourceAuthorizationMode.SERVICE_ONLY.value,),
            ),
        },
        source_provider=provider_id,
        source_resource_type=resource_type,
    )


def _authorized_envelope(
    *,
    provider_id: str,
    resource_type: str,
    handling_class: InformationHandlingClass,
    basis: tuple[str, ...],
) -> InformationAuthorizationEnvelope:
    return InformationAuthorizationEnvelope(
        handling_class=handling_class,
        decisions={
            action: _decision(
                action,
                allowed=True,
                reason_code=f"INFORMATION_{action.value.upper()}_ALLOWED",
                handling_class=handling_class,
                basis=basis,
            )
            for action in InformationAction
        },
        source_provider=provider_id,
        source_resource_type=resource_type,
    )


def _active_trusted_binding(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
):
    if bindings is None:
        return None
    return bindings.find_active_by_jason_identity(
        jason_identity_id=request.principal_id
    )


def _jason_managed_requester_authorization_proven(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
) -> bool:
    """Require positive identity/authority facts before requester release.

    This is the temporary IT Glue compatibility path approved for governed reads.
    Service-account fetch authority never becomes requester release authority by
    implication: authenticated human identity, an active trusted Microsoft/Jason
    binding, allowed JKD-001 authority, a validated authority context, observe-only
    permission, and Central Orchestrator EXECUTE mode are all required.
    """

    return bool(
        request.authority_allowed
        and request.authority_context_id
        and request.permission_mode == "observe"
        and request.requester_kind == "human"
        and request.orchestration_mode is OrchestrationMode.EXECUTE
        and _active_trusted_binding(request=request, bindings=bindings) is not None
    )


def _jason_managed_it_glue_envelope(
    *,
    capability_name: str,
    output: Mapping[str, Any],
) -> InformationAuthorizationEnvelope:
    sensitivity = assess_sensitive_evidence(output)
    handling = (
        InformationHandlingClass.DERIVED_OUTPUT_ONLY
        if sensitivity.sensitive
        else InformationHandlingClass.RELEASABLE
    )
    sensitivity_basis = tuple(
        sorted({f"sensitivity:{finding.kind.value}" for finding in sensitivity.findings})
    )
    return _authorized_envelope(
        provider_id=IT_GLUE_PROVIDER,
        resource_type=capability_name,
        handling_class=handling,
        basis=(
            SourceAuthorizationMode.JASON_MANAGED.value,
            "jkd001_authority_context",
            "trusted_microsoft_identity_binding",
            "central_orchestrator_governed_read",
        )
        + sensitivity_basis,
    )


def _relationship_data(resource: Mapping[str, Any], *names: str) -> list[Mapping[str, Any]] | None:
    relationships = resource.get("relationships")
    if not isinstance(relationships, Mapping):
        return None
    for name in names:
        relationship = relationships.get(name)
        if not isinstance(relationship, Mapping):
            continue
        data = relationship.get("data")
        if data is None:
            return []
        if isinstance(data, Mapping):
            return [data]
        if isinstance(data, list) and all(isinstance(item, Mapping) for item in data):
            return list(data)
    return None


def _trusted_principal_email(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
) -> tuple[str, str] | None:
    """Return a normalized email and its trust basis for source ACL evaluation.

    Runtime source authorization prefers the durable Microsoft->Jason binding keyed
    by the already-authenticated Jason principal. Request attributes are only a
    compatibility seam for tests/non-runtime callers that do not provide a binding
    resolver. This prevents a caller-supplied email from overriding trusted identity.
    """

    if bindings is not None:
        binding = bindings.find_active_by_jason_identity(
            jason_identity_id=request.principal_id
        )
        if binding is None:
            return None
        email = str(getattr(binding, "email_address", "") or "").strip().casefold()
        if not email:
            return None
        return email, "trusted_microsoft_identity_binding"

    email = request.principal_attributes.get("email", "").strip().casefold()
    if not email:
        return None
    return email, "trusted_request_principal_attribute"


def _it_glue_document_acl_envelope(
    *,
    request: OrchestrationRequest,
    payload: Mapping[str, Any],
    bindings: TrustedPrincipalBindingResolver | None,
) -> InformationAuthorizationEnvelope:
    resolved_principal = _trusted_principal_email(request=request, bindings=bindings)
    if resolved_principal is None:
        return _service_only_envelope(
            provider_id=IT_GLUE_PROVIDER,
            resource_type="document",
            reason_code="SOURCE_PRINCIPAL_EMAIL_REQUIRED",
        )
    email, principal_basis = resolved_principal

    resource = payload.get("data")
    if not isinstance(resource, Mapping):
        return _service_only_envelope(
            provider_id=IT_GLUE_PROVIDER,
            resource_type="document",
            reason_code="IT_GLUE_DOCUMENT_AUTHORIZATION_PAYLOAD_INVALID",
        )

    attributes = resource.get("attributes")
    if not isinstance(attributes, Mapping) or not isinstance(attributes.get("restricted"), bool):
        return _service_only_envelope(
            provider_id=IT_GLUE_PROVIDER,
            resource_type="document",
            reason_code="IT_GLUE_DOCUMENT_RESTRICTION_STATE_UNKNOWN",
        )

    authorized_refs = _relationship_data(resource, "authorized_users", "authorized-users")
    if authorized_refs is None:
        return _service_only_envelope(
            provider_id=IT_GLUE_PROVIDER,
            resource_type="document",
            reason_code="IT_GLUE_AUTHORIZED_USERS_RELATIONSHIP_REQUIRED",
        )

    authorized_ids = {
        str(item.get("id"))
        for item in authorized_refs
        if item.get("id") is not None
    }
    included = payload.get("included")
    if not isinstance(included, list):
        included = []

    matching_authorized_user = False
    for item in included:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("id")) not in authorized_ids:
            continue
        item_type = str(item.get("type", "")).casefold()
        if item_type not in {"user", "users", "authorized-user", "authorized-users"}:
            continue
        user_attributes = item.get("attributes")
        if not isinstance(user_attributes, Mapping):
            continue
        candidate = str(user_attributes.get("email", "")).strip().casefold()
        if candidate and candidate == email:
            matching_authorized_user = True
            break

    if not matching_authorized_user:
        return _service_only_envelope(
            provider_id=IT_GLUE_PROVIDER,
            resource_type="document",
            reason_code="IT_GLUE_DOCUMENT_ACCESS_NOT_ESTABLISHED",
        )

    sensitivity = assess_sensitive_evidence(attributes)
    handling_class = (
        InformationHandlingClass.DERIVED_OUTPUT_ONLY
        if sensitivity.sensitive
        else InformationHandlingClass.RELEASABLE
    )
    sensitivity_basis = tuple(
        sorted({f"sensitivity:{finding.kind.value}" for finding in sensitivity.findings})
    )
    return _authorized_envelope(
        provider_id=IT_GLUE_PROVIDER,
        resource_type="document",
        handling_class=handling_class,
        basis=(
            SourceAuthorizationMode.ACL_MIRRORED.value,
            "it_glue_authorized_users",
            principal_basis,
            "authenticated_principal_email_match",
        ) + sensitivity_basis,
    )


def _sanitize_it_glue_document_read_output(output: Mapping[str, Any]) -> dict[str, Any]:
    """Remove source ACL material after it has served the authorization decision."""

    result = dict(output)
    payload = result.get("data")
    if not isinstance(payload, Mapping):
        return result

    sanitized_payload = dict(payload)
    sanitized_payload.pop("included", None)
    resource = payload.get("data")
    if isinstance(resource, Mapping):
        sanitized_resource = dict(resource)
        relationships = resource.get("relationships")
        if isinstance(relationships, Mapping):
            sanitized_relationships = {
                str(key): value
                for key, value in relationships.items()
                if str(key) not in _DOCUMENT_AUTHORIZATION_RELATIONSHIPS
            }
            if sanitized_relationships:
                sanitized_resource["relationships"] = sanitized_relationships
            else:
                sanitized_resource.pop("relationships", None)
        sanitized_payload["data"] = sanitized_resource
    result["data"] = sanitized_payload
    return result


def _sanitize_it_glue_document_search_output(output: Mapping[str, Any]) -> dict[str, Any]:
    """Defense in depth: document search never carries document body content."""

    result = dict(output)
    payload = result.get("data")
    if not isinstance(payload, Mapping):
        return result

    sanitized_payload = dict(payload)
    records = payload.get("data")
    if isinstance(records, list):
        sanitized_records: list[Any] = []
        for record in records:
            if not isinstance(record, Mapping):
                sanitized_records.append(record)
                continue
            sanitized_record = dict(record)
            attributes = record.get("attributes")
            if isinstance(attributes, Mapping):
                sanitized_record["attributes"] = {
                    str(key): value
                    for key, value in attributes.items()
                    if str(key) not in _SENSITIVE_DOCUMENT_SEARCH_ATTRIBUTE_KEYS
                }
            sanitized_record.pop("included", None)
            sanitized_records.append(sanitized_record)
        sanitized_payload["data"] = sanitized_records

    sanitized_payload.pop("included", None)
    result["data"] = sanitized_payload
    return result


@dataclass(frozen=True, slots=True)
class ProviderReadInformationAuthorizingInvoker:
    """Attach source-aware information authorization to every provider read.

    Unknown provider/resource authorization intentionally becomes service-only. This
    lets Jason retrieve evidence for an authorized execution when needed while
    preventing the service identity's privilege from becoming requester disclosure
    authority.

    IT Glue document reads retain the provider-native ACL-mirrored path when positive
    source authorization is available. The approved temporary Jason-managed path is a
    bounded fallback for registered IT Glue read capabilities and requires the same
    positive identity, authority, observe-only, and Central Orchestrator facts used by
    the temporary Autotask requester-authorization path.
    """

    delegate: CapabilityInvoker
    bindings: TrustedPrincipalBindingResolver | None = None

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        invocation = self.delegate.invoke(request=request, resolution=resolution)
        provider_id = (resolution.selected_provider_id or "").strip()

        if provider_id == IT_GLUE_PROVIDER and resolution.capability_name == DOCUMENTATION_DOCUMENT_READ:
            payload = invocation.output.get("data")
            authorization = (
                _it_glue_document_acl_envelope(
                    request=request,
                    payload=payload,
                    bindings=self.bindings,
                )
                if isinstance(payload, Mapping)
                else _service_only_envelope(
                    provider_id=provider_id,
                    resource_type="document",
                    reason_code="IT_GLUE_DOCUMENT_AUTHORIZATION_PAYLOAD_INVALID",
                )
            )
            output = _sanitize_it_glue_document_read_output(invocation.output)

            # Prefer provider-native ACL evidence when it positively authorizes release.
            # Otherwise the approved temporary Jason-managed path may authorize the same
            # registered read only after all independent requester/governance checks pass.
            if (
                not authorization.require_allowed(InformationAction.RELEASE).allowed
                and resolution.capability_name in IT_GLUE_CAPABILITIES
                and _jason_managed_requester_authorization_proven(
                    request=request,
                    bindings=self.bindings,
                )
            ):
                authorization = _jason_managed_it_glue_envelope(
                    capability_name=resolution.capability_name,
                    output=output,
                )
        elif provider_id == IT_GLUE_PROVIDER and resolution.capability_name == DOCUMENTATION_DOCUMENT_SEARCH:
            output = _sanitize_it_glue_document_search_output(invocation.output)
            if (
                resolution.capability_name in IT_GLUE_CAPABILITIES
                and _jason_managed_requester_authorization_proven(
                    request=request,
                    bindings=self.bindings,
                )
            ):
                authorization = _jason_managed_it_glue_envelope(
                    capability_name=resolution.capability_name,
                    output=output,
                )
            else:
                authorization = _service_only_envelope(
                    provider_id=provider_id,
                    resource_type="document-search",
                    reason_code="IT_GLUE_DOCUMENT_SEARCH_SOURCE_AUTHORIZATION_UNVERIFIED",
                )
        elif (
            provider_id == IT_GLUE_PROVIDER
            and resolution.capability_name in IT_GLUE_CAPABILITIES
            and _jason_managed_requester_authorization_proven(
                request=request,
                bindings=self.bindings,
            )
        ):
            output = dict(invocation.output)
            authorization = _jason_managed_it_glue_envelope(
                capability_name=resolution.capability_name,
                output=output,
            )
        else:
            authorization = _service_only_envelope(
                provider_id=provider_id or "unknown",
                resource_type=resolution.capability_name,
            )
            output = dict(invocation.output)

        return InvocationResult(
            output=output,
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=authorization,
        )
