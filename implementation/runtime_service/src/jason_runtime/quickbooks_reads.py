from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.quickbooks.connector import (
    QUICKBOOKS_ACCOUNT_SEARCH,
    QUICKBOOKS_BALANCE_SHEET_READ,
    QUICKBOOKS_BILL_SEARCH,
    QUICKBOOKS_COMPANY_READ,
    QUICKBOOKS_CUSTOMER_SEARCH,
    QUICKBOOKS_INVOICE_SEARCH,
    QUICKBOOKS_PROFIT_LOSS_READ,
    QUICKBOOKS_PROVIDER,
    QUICKBOOKS_VENDOR_SEARCH,
    QuickBooksConnector,
)
from connectors.quickbooks.oauth import QuickBooksOAuthStore
from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import ExecutionProviderRegistryService
from kernel.resolution import CapabilityResolutionResult
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import (
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
    InformationRemediation,
)
from orchestrator.information_sensitivity import assess_sensitive_evidence
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_information_authorizer import (
    TrustedPrincipalBindingResolver,
)
from orchestrator.quickbooks_capability_catalog import (
    ACCOUNTING_ACCOUNT_SEARCH,
    ACCOUNTING_BALANCE_SHEET_READ,
    ACCOUNTING_BILL_SEARCH,
    ACCOUNTING_COMPANY_READ,
    ACCOUNTING_CUSTOMER_SEARCH,
    ACCOUNTING_INVOICE_SEARCH,
    ACCOUNTING_PROFIT_LOSS_READ,
    ACCOUNTING_VENDOR_SEARCH,
    QUICKBOOKS_CAPABILITIES,
    register_quickbooks_read_foundation,
)
from orchestrator.service import CapabilityInvoker, InvocationResult

from .quickbooks_read_activation import apply_quickbooks_read_activation_from_env


_PROVIDER_CAPABILITY_MAP = {
    (QUICKBOOKS_PROVIDER, ACCOUNTING_COMPANY_READ): QUICKBOOKS_COMPANY_READ,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_ACCOUNT_SEARCH): QUICKBOOKS_ACCOUNT_SEARCH,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_VENDOR_SEARCH): QUICKBOOKS_VENDOR_SEARCH,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_CUSTOMER_SEARCH): QUICKBOOKS_CUSTOMER_SEARCH,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_INVOICE_SEARCH): QUICKBOOKS_INVOICE_SEARCH,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_BILL_SEARCH): QUICKBOOKS_BILL_SEARCH,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_PROFIT_LOSS_READ): QUICKBOOKS_PROFIT_LOSS_READ,
    (QUICKBOOKS_PROVIDER, ACCOUNTING_BALANCE_SHEET_READ): QUICKBOOKS_BALANCE_SHEET_READ,
}


def _denied_envelope(capability_name: str, reason: str) -> InformationAuthorizationEnvelope:
    handling = InformationHandlingClass.EXECUTION_ONLY
    decisions = {}
    for action in InformationAction:
        allowed = action is InformationAction.FETCH
        decisions[action] = InformationAuthorizationDecision(
            action=action,
            allowed=allowed,
            reason_code=(
                "SERVICE_IDENTITY_FETCH_ALLOWED"
                if allowed
                else reason
            ),
            handling_class=handling,
            remediation=(
                InformationRemediation.NONE
                if allowed
                else InformationRemediation.REQUEST_ACCESS
            ),
            policy_ids=("quickbooks-information-authorization-v1",),
            authorization_basis=(
                "quickbooks_oauth_service_identity",
                "fail_closed_requester_release",
            ),
        )
    return InformationAuthorizationEnvelope(
        handling_class=handling,
        decisions=decisions,
        source_provider=QUICKBOOKS_PROVIDER,
        source_resource_type=capability_name,
        source_scope="oauth_bound_realm",
    )


def _allowed_envelope(
    capability_name: str,
    output,
) -> InformationAuthorizationEnvelope:
    sensitivity = assess_sensitive_evidence(output)
    handling = (
        InformationHandlingClass.DERIVED_OUTPUT_ONLY
        if sensitivity.sensitive
        else InformationHandlingClass.RELEASABLE
    )
    decisions = {
        action: InformationAuthorizationDecision(
            action=action,
            allowed=True,
            reason_code=f"INFORMATION_{action.value.upper()}_ALLOWED",
            handling_class=handling,
            policy_ids=("quickbooks-information-authorization-v1",),
            authorization_basis=(
                "jason_managed",
                "aot_human_requester",
                "trusted_microsoft_identity_binding",
                "jkd001_authority_context",
                "central_orchestrator_governed_read",
                "oauth_bound_quickbooks_realm",
            ),
        )
        for action in InformationAction
    }
    return InformationAuthorizationEnvelope(
        handling_class=handling,
        decisions=decisions,
        source_provider=QUICKBOOKS_PROVIDER,
        source_resource_type=capability_name,
        source_scope="oauth_bound_realm",
    )


@dataclass(frozen=True, slots=True)
class QuickBooksInformationAuthorizingInvoker:
    delegate: CapabilityInvoker
    bindings: TrustedPrincipalBindingResolver | None

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        invocation = self.delegate.invoke(request=request, resolution=resolution)
        binding = (
            self.bindings.find_active_by_jason_identity(
                jason_identity_id=request.principal_id
            )
            if self.bindings is not None
            else None
        )
        requester_authorized = bool(
            resolution.selected_provider_id == QUICKBOOKS_PROVIDER
            and request.organization_id.strip().casefold() == "aot"
            and request.authority_allowed
            and request.authority_context_id
            and request.permission_mode == "observe"
            and request.requester_kind == "human"
            and request.orchestration_mode is OrchestrationMode.EXECUTE
            and binding is not None
        )
        authorization = (
            _allowed_envelope(resolution.capability_name, invocation.output)
            if requester_authorized
            else _denied_envelope(
                resolution.capability_name,
                "QUICKBOOKS_REQUESTER_AUTHORIZATION_UNVERIFIED",
            )
        )
        return InvocationResult(
            output=dict(invocation.output),
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=authorization,
        )


def register_quickbooks_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
):
    register_quickbooks_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=now,
    )
    return apply_quickbooks_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )


def build_quickbooks_read_invoker(
    *,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    oauth_db: Path,
    transport: HttpTransport,
    audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver | None,
    environment: str = "sandbox",
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = QuickBooksConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        oauth_store=QuickBooksOAuthStore(
            oauth_db,
            require_encryption=(environment == "production"),
        ),
        expected_environment=environment,
    )
    delegate = GovernedConnectorCapabilityInvoker(
        connectors={QUICKBOOKS_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )
    return QuickBooksInformationAuthorizingInvoker(
        delegate=delegate,
        bindings=bindings,
    )


def register_quickbooks_read_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    for capability in sorted(QUICKBOOKS_CAPABILITIES):
        invokers.register(capability, invoker)
