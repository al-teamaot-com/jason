from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import InformationAction, InformationRemediation
from orchestrator.provider_read_capability_catalog import (
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
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


def _request(capability, *, email="al@example.com"):
    attributes = {} if email is None else {"email": email}
    return OrchestrationRequest(
        execution_id="exec-provider-info",
        correlation_id="corr-provider-info",
        principal_id="person-al",
        organization_id="org-aot",
        client_id="client-aot",
        capability_name=capability,
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
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
        principal_attributes=attributes,
        authority_context_id="ctx-provider-info",
    )


def _resolution(capability, provider="it_glue"):
    return CapabilityResolutionResult(
        execution_id="exec-provider-info",
        correlation_id="corr-provider-info",
        capability_name=capability,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
        reason_codes=("resolved",),
        eligible_provider_ids=(provider,),
        selected_provider_id=provider,
    )


def _authorized_document_payload(email="al@example.com"):
    return {
        "provider": "it_glue",
        "provider_capability": "it_glue.document.get",
        "data": {
            "data": {
                "id": "73",
                "type": "documents",
                "attributes": {
                    "name": "Network Notes",
                    "restricted": True,
                    "sections": [{"attributes": {"content": "body"}}],
                },
                "relationships": {
                    "authorized-users": {
                        "data": [{"id": "35", "type": "users"}],
                    }
                },
            },
            "included": [
                {
                    "id": "35",
                    "type": "users",
                    "attributes": {"email": email},
                }
            ],
        },
    }


def test_exact_it_glue_document_read_allows_matching_effective_authorized_user() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(_authorized_document_payload())
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_READ),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_READ),
    )

    envelope = invocation.information_authorization
    assert envelope is not None
    assert all(envelope.require_allowed(action).allowed for action in InformationAction)
    assert "acl_mirrored" in envelope.require_allowed(InformationAction.RELEASE).authorization_basis


def test_it_glue_document_read_denies_when_principal_is_not_authorized() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(_authorized_document_payload("other@example.com"))
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_READ),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_READ),
    )

    decision = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert decision.allowed is False
    assert decision.reason_code == "IT_GLUE_DOCUMENT_ACCESS_NOT_ESTABLISHED"
    assert decision.remediation is InformationRemediation.REQUEST_ACCESS


def test_it_glue_document_read_denies_when_authenticated_email_is_missing() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(_authorized_document_payload())
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_READ, email=None),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_READ),
    )

    decision = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert decision.allowed is False
    assert decision.reason_code == "SOURCE_PRINCIPAL_EMAIL_REQUIRED"


def test_it_glue_document_read_denies_when_authorized_users_relationship_is_missing() -> None:
    output = _authorized_document_payload()
    output["data"]["data"]["relationships"] = {}
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(output)
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_READ),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_READ),
    )

    decision = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert decision.allowed is False
    assert decision.reason_code == "IT_GLUE_AUTHORIZED_USERS_RELATIONSHIP_REQUIRED"


def test_document_search_strips_body_content_and_still_denies_until_per_record_acl_is_verified() -> None:
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
        delegate=_Delegate(output)
    ).invoke(
        request=_request(DOCUMENTATION_DOCUMENT_SEARCH),
        resolution=_resolution(DOCUMENTATION_DOCUMENT_SEARCH),
    )

    attributes = invocation.output["data"]["data"][0]["attributes"]
    assert attributes == {"name": "Network Notes", "restricted": True}
    assert "included" not in invocation.output["data"]
    decision = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert decision.allowed is False
    assert decision.reason_code == "IT_GLUE_DOCUMENT_SEARCH_SOURCE_AUTHORIZATION_UNVERIFIED"


def test_unknown_provider_read_is_service_only_and_non_releasable_by_default() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate({"provider": "autotask", "data": {"items": []}})
    ).invoke(
        request=_request("service.ticket.search"),
        resolution=_resolution("service.ticket.search", provider="autotask"),
    )

    envelope = invocation.information_authorization
    assert envelope.require_allowed(InformationAction.FETCH).allowed is True
    assert envelope.require_allowed(InformationAction.RELEASE).allowed is False
    assert envelope.require_allowed(InformationAction.RELEASE).remediation is InformationRemediation.REQUEST_ACCESS
