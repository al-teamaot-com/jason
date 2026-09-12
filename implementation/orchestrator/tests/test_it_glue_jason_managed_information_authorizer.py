from __future__ import annotations

from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import InformationAction, InformationHandlingClass
from orchestrator.provider_read_capability_catalog import (
    DOCUMENTATION_CONFIGURATION_READ,
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_ORGANIZATION_SEARCH,
)
from orchestrator.provider_read_information_authorizer import (
    ProviderReadInformationAuthorizingInvoker,
)
from orchestrator.service import InvocationResult


class _Delegate:
    def __init__(self, output):
        self.output = output

    def invoke(self, *, request, resolution):
        return InvocationResult(output=self.output)


class _Binding:
    email_address = "al@example.com"


class _Bindings:
    def __init__(self, value=_Binding()):
        self.value = value

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        return self.value if jason_identity_id == "person-al" else None


def _request(
    capability: str,
    *,
    authority_allowed: bool = True,
    authority_context_id: str | None = "ctx-it-glue-info",
    permission_mode: str = "observe",
    requester_kind: str = "human",
) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-it-glue-info",
        correlation_id="corr-it-glue-info",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name=capability,
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=authority_allowed,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        requester_kind=requester_kind,
        permission_mode=permission_mode,
        authority_context_id=authority_context_id,
    )


def _resolution(capability: str, provider: str = "it_glue") -> CapabilityResolutionResult:
    return CapabilityResolutionResult(
        execution_id="exec-it-glue-info",
        correlation_id="corr-it-glue-info",
        capability_name=capability,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
        reason_codes=("resolved",),
        eligible_provider_ids=(provider,),
        selected_provider_id=provider,
    )


def test_jason_managed_it_glue_read_is_releasable_after_trusted_authority_context() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate({"provider": "it_glue", "data": {"items": [{"id": "42"}]}}),
        bindings=_Bindings(),
    ).invoke(
        request=_request(DOCUMENTATION_ORGANIZATION_SEARCH),
        resolution=_resolution(DOCUMENTATION_ORGANIZATION_SEARCH),
    )

    envelope = invocation.information_authorization
    assert envelope is not None
    assert envelope.handling_class is InformationHandlingClass.RELEASABLE
    assert all(envelope.require_allowed(action).allowed for action in InformationAction)
    release = envelope.require_allowed(InformationAction.RELEASE)
    assert "jason_managed" in release.authorization_basis
    assert "jkd001_authority_context" in release.authorization_basis
    assert "trusted_microsoft_identity_binding" in release.authorization_basis
    assert "central_orchestrator_governed_read" in release.authorization_basis


def test_jason_managed_it_glue_uses_registered_catalog_not_resource_allowlist() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate({"provider": "it_glue", "data": {"item": {"id": "9"}}}),
        bindings=_Bindings(),
    ).invoke(
        request=_request(DOCUMENTATION_CONFIGURATION_READ),
        resolution=_resolution(DOCUMENTATION_CONFIGURATION_READ),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is True
    assert "jason_managed" in release.authorization_basis


def test_missing_trusted_binding_preserves_service_only_denial() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate({"provider": "it_glue", "data": {"items": []}}),
        bindings=_Bindings(None),
    ).invoke(
        request=_request(DOCUMENTATION_ORGANIZATION_SEARCH),
        resolution=_resolution(DOCUMENTATION_ORGANIZATION_SEARCH),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is False


@pytest.mark.parametrize(
    "orchestration_request",
    [
        _request(DOCUMENTATION_ORGANIZATION_SEARCH, authority_allowed=False),
        _request(DOCUMENTATION_ORGANIZATION_SEARCH, authority_context_id=None),
        _request(DOCUMENTATION_ORGANIZATION_SEARCH, permission_mode="execute"),
        _request(DOCUMENTATION_ORGANIZATION_SEARCH, requester_kind="service"),
    ],
)
def test_jason_managed_it_glue_fails_closed_without_positive_requester_authority(
    orchestration_request: OrchestrationRequest,
) -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate({"provider": "it_glue", "data": {"items": []}}),
        bindings=_Bindings(),
    ).invoke(
        request=orchestration_request,
        resolution=_resolution(DOCUMENTATION_ORGANIZATION_SEARCH),
    )

    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


def test_sensitive_jason_managed_it_glue_output_is_derived_only() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(
            {
                "provider": "it_glue",
                "data": {"items": [{"name": "Credential", "password": "example-secret"}]},
            }
        ),
        bindings=_Bindings(),
    ).invoke(
        request=_request(DOCUMENTATION_ORGANIZATION_SEARCH),
        resolution=_resolution(DOCUMENTATION_ORGANIZATION_SEARCH),
    )

    envelope = invocation.information_authorization
    assert envelope.handling_class is InformationHandlingClass.DERIVED_OUTPUT_ONLY
    assert envelope.require_allowed(InformationAction.RELEASE).allowed is True


def test_document_search_remains_sanitized_under_jason_managed_release() -> None:
    output = {
        "provider": "it_glue",
        "provider_capability": "it_glue.document.search",
        "data": {
            "data": [
                {
                    "id": "73",
                    "type": "documents",
                    "attributes": {
                        "name": "Network Notes",
                        "restricted": True,
                        "content": "secret body",
                        "rendered-content": "rendered secret body",
                        "sections": [{"content": "section secret"}],
                    },
                }
            ],
            "included": [{"type": "users", "attributes": {"email": "al@example.com"}}],
        },
    }
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(output),
        bindings=_Bindings(),
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_SEARCH),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_SEARCH),
    )

    attributes = invocation.output["data"]["data"][0]["attributes"]
    assert attributes == {"name": "Network Notes", "restricted": True}
    assert "included" not in invocation.output["data"]
    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is True
    assert "jason_managed" in release.authorization_basis


def test_document_read_explicit_acl_denial_is_not_overridden_by_jason_managed_release() -> None:
    output = {
        "provider": "it_glue",
        "provider_capability": "it_glue.document.read",
        "data": {
            "data": {
                "id": "73",
                "type": "documents",
                "attributes": {
                    "name": "Restricted Network Notes",
                    "restricted": True,
                },
                "relationships": {
                    "authorized_users": {
                        "data": [{"id": "user-other", "type": "users"}],
                    }
                },
            },
            "included": [
                {
                    "id": "user-other",
                    "type": "users",
                    "attributes": {"email": "other@example.com"},
                }
            ],
        },
    }
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(output),
        bindings=_Bindings(),
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_READ),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_READ),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is False
    assert release.reason_code == "IT_GLUE_DOCUMENT_ACCESS_NOT_ESTABLISHED"
    assert "jason_managed" not in release.authorization_basis
    assert "included" not in invocation.output["data"]
    relationships = invocation.output["data"]["data"].get("relationships", {})
    assert "authorized_users" not in relationships
