from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import InformationAction
from orchestrator.provider_read_capability_catalog import DOCUMENTATION_DOCUMENT_READ
from orchestrator.provider_read_information_authorizer import ProviderReadInformationAuthorizingInvoker
from orchestrator.service import InvocationResult
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from jason_runtime.provider_reads import runtime_principal_bindings_from_env


class _Delegate:
    def __init__(self, output):
        self.output = output

    def invoke(self, *, request, resolution):
        return InvocationResult(output=self.output)


class _BindingResolver:
    def __init__(self, binding):
        self.binding = binding

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        if self.binding is None:
            return None
        if self.binding.jason_identity_id != jason_identity_id:
            return None
        return self.binding


def _request(*, email: str | None = None) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-trusted-binding",
        correlation_id="corr-trusted-binding",
        principal_id="person-al",
        organization_id="org-aot",
        client_id="client-aot",
        capability_name=DOCUMENTATION_DOCUMENT_READ,
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
        principal_attributes={} if email is None else {"email": email},
        authority_context_id="ctx-trusted-binding",
    )


def _resolution() -> CapabilityResolutionResult:
    return CapabilityResolutionResult(
        execution_id="exec-trusted-binding",
        correlation_id="corr-trusted-binding",
        capability_name=DOCUMENTATION_DOCUMENT_READ,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
        reason_codes=("resolved",),
        eligible_provider_ids=("it_glue",),
        selected_provider_id="it_glue",
    )


def _document_payload(email: str = "al@example.com") -> dict:
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
                    "sections": [{"attributes": {"content": "Printer is configured by IP."}}],
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


def _binding(email: str = "al@example.com") -> MicrosoftIdentityBinding:
    return MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-aot",
        microsoft_object_id="object-al",
        jason_identity_id="person-al",
        client_id="client-aot",
        email_address=email,
        status="active",
    )


def test_runtime_binding_store_is_disabled_when_path_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("JASON_TEAMS_IDENTITY_BINDINGS_DB", raising=False)
    assert runtime_principal_bindings_from_env() is None


def test_runtime_binding_store_resolves_one_active_bound_identity(monkeypatch, tmp_path) -> None:
    path = tmp_path / "bindings.sqlite3"
    monkeypatch.setenv("JASON_TEAMS_IDENTITY_BINDINGS_DB", str(path))
    store = runtime_principal_bindings_from_env()
    assert store is not None
    try:
        store.put(_binding())
        resolved = store.find_active_by_jason_identity(jason_identity_id="person-al")
        assert resolved is not None
        assert resolved.email_address == "al@example.com"
    finally:
        store.close()


def test_runtime_binding_store_fails_closed_on_ambiguous_active_bindings(monkeypatch, tmp_path) -> None:
    path = tmp_path / "bindings.sqlite3"
    monkeypatch.setenv("JASON_TEAMS_IDENTITY_BINDINGS_DB", str(path))
    store = runtime_principal_bindings_from_env()
    assert store is not None
    try:
        store.put(_binding())
        store.put(
            MicrosoftIdentityBinding(
                microsoft_tenant_id="tenant-aot",
                microsoft_object_id="object-al-second",
                jason_identity_id="person-al",
                client_id="client-aot",
                email_address="al.secondary@example.com",
                status="active",
            )
        )
        assert store.find_active_by_jason_identity(jason_identity_id="person-al") is None
    finally:
        store.close()


def test_trusted_binding_overrides_untrusted_request_email_for_acl_decision() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(_document_payload()),
        bindings=_BindingResolver(_binding()),
    ).invoke(
        request=_request(email="attacker@example.com"),
        resolution=_resolution(),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is True
    assert "trusted_microsoft_identity_binding" in release.authorization_basis
    assert "attacker@example.com" not in repr(invocation.information_authorization)


def test_missing_trusted_binding_denies_even_when_request_email_matches_acl() -> None:
    invocation = ProviderReadInformationAuthorizingInvoker(
        delegate=_Delegate(_document_payload()),
        bindings=_BindingResolver(None),
    ).invoke(
        request=_request(email="al@example.com"),
        resolution=_resolution(),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is False
    assert release.reason_code == "SOURCE_PRINCIPAL_EMAIL_REQUIRED"
