"""Requester-bound governed Constant Contact read runtime integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from connectors.constant_contact.connector import (
    ConstantContactConnector, PROVIDER, READ_CAPABILITIES,
)
from connectors.core.contracts import AuditSink, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import ExecutionProviderRegistryService
from kernel.resolution import CapabilityResolutionResult
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.constant_contact_capability_catalog import register_foundation
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import (
    InformationAction, InformationAuthorizationDecision,
    InformationAuthorizationEnvelope, InformationHandlingClass,
    InformationRemediation,
)
from orchestrator.information_sensitivity import assess_sensitive_evidence
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_information_authorizer import TrustedPrincipalBindingResolver
from orchestrator.service import CapabilityInvoker, InvocationResult

from .constant_contact_activation import apply_read_from_env


@dataclass(frozen=True, slots=True)
class RequesterBoundConstantContactInvoker:
    delegate: CapabilityInvoker
    bindings: TrustedPrincipalBindingResolver | None

    def invoke(self, *, request: OrchestrationRequest,
               resolution: CapabilityResolutionResult) -> InvocationResult:
        invocation = self.delegate.invoke(request=request, resolution=resolution)
        binding = (
            self.bindings.find_active_by_jason_identity(
                jason_identity_id=request.principal_id)
            if self.bindings is not None else None
        )
        allowed = bool(
            resolution.selected_provider_id == PROVIDER
            and request.organization_id.strip().casefold() == "aot"
            and request.authority_allowed
            and request.authority_context_id
            and request.permission_mode == "observe"
            and request.requester_kind == "human"
            and request.orchestration_mode is OrchestrationMode.EXECUTE
            and binding is not None
        )
        if allowed:
            handling = (
                InformationHandlingClass.DERIVED_OUTPUT_ONLY
                if assess_sensitive_evidence(invocation.output).sensitive
                else InformationHandlingClass.RELEASABLE
            )
        else:
            handling = InformationHandlingClass.EXECUTION_ONLY
        decisions = {
            action: InformationAuthorizationDecision(
                action=action,
                allowed=(allowed or action is InformationAction.FETCH),
                reason_code=(
                    "CONSTANT_CONTACT_REQUESTER_AUTHORIZED" if allowed
                    else "CONSTANT_CONTACT_REQUESTER_UNVERIFIED"
                ),
                handling_class=handling,
                remediation=(
                    InformationRemediation.NONE if allowed or action is InformationAction.FETCH
                    else InformationRemediation.REQUEST_ACCESS
                ),
                policy_ids=("constant-contact-information-authorization-v1",),
                authorization_basis=(
                    "jason_governed_read", "trusted_microsoft_identity_binding",
                    "aot_internal_oauth_account",
                ),
            ) for action in InformationAction
        }
        return InvocationResult(
            output=dict(invocation.output),
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=InformationAuthorizationEnvelope(
                handling_class=handling,
                decisions=decisions,
                source_provider=PROVIDER,
                source_resource_type=resolution.capability_name,
                source_scope="aot_internal_oauth_account",
            ),
        )


def register_runtime_foundation(*, capabilities: CapabilityRegistryService,
                                providers: ExecutionProviderRegistryService,
                                now: datetime):
    register_foundation(capabilities=capabilities, providers=providers, now=now)
    return apply_read_from_env(capabilities=capabilities, providers=providers)


def build_read_invoker(*, openbao_url: str, role_id_path: Path, secret_id_path: Path,
                       oauth_db: Path, transport: HttpTransport, audit: AuditSink,
                       bindings: TrustedPrincipalBindingResolver | None) -> CapabilityInvoker:
    secret_resolver = OpenBaoSecretResolver(
        base_url=openbao_url, role_id_path=role_id_path, secret_id_path=secret_id_path,
    )
    connector = ConstantContactConnector(
        secrets=secret_resolver, transport=transport, audit=audit, oauth_db=oauth_db,
    )
    delegate = GovernedConnectorCapabilityInvoker(
        connectors={PROVIDER: connector},
        provider_capability_map={(PROVIDER, name): name for name in READ_CAPABILITIES},
    )
    return RequesterBoundConstantContactInvoker(delegate=delegate, bindings=bindings)


def register_read_invokers(*, invokers: CapabilityInvokerRegistry,
                           invoker: CapabilityInvoker) -> None:
    for capability in sorted(READ_CAPABILITIES):
        invokers.register(capability, invoker)
