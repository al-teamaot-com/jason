"""Optional governed SharePoint invoker — dedicated app execution, Owner-bound release.

The human requester authorizes the action, but the Microsoft Graph provider
always executes under Jason's own validated certificate-backed app identity.
No delegated Microsoft/ChatGPT user tokens are borrowed or impersonated.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.microsoft_graph.aot_site_document_policy import AotSharePointSiteDocumentAuthorizer
from connectors.microsoft_graph.sharepoint_connector import GovernedSharePointConnector
from kernel.client_boundaries import SQLiteClientBoundaryRepository
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode
from orchestrator.information_authorization import (
    InformationAction, InformationAuthorizationDecision,
    InformationAuthorizationEnvelope, InformationHandlingClass, InformationRemediation,
)
from orchestrator.provider_read_information_authorizer import TrustedPrincipalBindingResolver
from orchestrator.sharepoint_capability_catalog import SHAREPOINT_CAPABILITIES, SHAREPOINT_PROVIDER
from orchestrator.service import InvocationResult
from orchestrator.invokers import CapabilityInvokerRegistry

from .microsoft_sharepoint import (
    build_microsoft_sharepoint_runtime, build_sharepoint_site_management,
    require_validated_sharepoint_service_boundary,
)


class _NoClientBindings:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        return None


@dataclass(frozen=True)
class _ValidatedAotServiceBinding:
    principal_id: str
    tenant_id: str

    def find_active_by_jason_service_identity(self, *, jason_identity_id, organization_id):
        if organization_id != "aot" or jason_identity_id != self.principal_id:
            return None
        return SimpleNamespace(status="active", organization_id="aot",
                               jason_identity_id=self.principal_id,
                               microsoft_tenant_id=self.tenant_id,
                               profile="aot-approved-site-read")


class _NoContentRelease:
    def authorized(self, **kwargs):
        return False


def _information_policy(capability: str) -> InformationAuthorizationEnvelope:
    # Exact-document financial content is DENIED until separately authorized.
    metadata = capability != "knowledge.document.content.read"
    classification = (InformationHandlingClass.METADATA_ONLY if metadata
                      else InformationHandlingClass.EXECUTION_ONLY)
    return InformationAuthorizationEnvelope(
        handling_class=classification,
        decisions={
            action: InformationAuthorizationDecision(
                action=action,
                allowed=metadata or action is InformationAction.FETCH,
                remediation=(InformationRemediation.NONE if metadata or action is InformationAction.FETCH
                             else InformationRemediation.REQUEST_ACCESS),
                reason_code=("SHAREPOINT_AOT_OWNER_METADATA_ALLOWED" if metadata
                             else "SHAREPOINT_CONTENT_RELEASE_NOT_APPROVED"),
                handling_class=classification,
                policy_ids=("aot-sharepoint-site-access-v1",),
                authorization_basis=("dedicated_jason_app_only_graph",
                                     "validated_owner_binding",
                                     "site_policy_current_readback"),
            ) for action in InformationAction
        },
        source_provider=SHAREPOINT_PROVIDER,
        source_resource_type=capability,
        source_scope="aot_sharepoint_enabled_site",
    )


@dataclass(frozen=True)
class AotSharePointAuthorizingInvoker:
    delegate: GovernedConnectorCapabilityInvoker
    approved_owner_ids: frozenset[str]
    original_identity_bindings: TrustedPrincipalBindingResolver
    app_service_principal_id: str

    def invoke(self, *, request, resolution):
        if (resolution.selected_provider_id != SHAREPOINT_PROVIDER
                or request.capability_name not in SHAREPOINT_CAPABILITIES
                or request.organization_id != "aot"
                or request.client_id is not None
                or request.requester_kind != "human"
                or request.permission_mode != "observe"
                or request.orchestration_mode is not OrchestrationMode.EXECUTE
                or not request.authority_allowed
                or not request.authority_context_id
                or request.principal_id not in self.approved_owner_ids):
            raise PermissionError("SharePoint AOT Owner governed read required")
        requester_binding = self.original_identity_bindings.find_active_by_jason_identity(
            jason_identity_id=request.principal_id)
        if requester_binding is None:
            raise PermissionError("SharePoint requester identity not verified")
        # User identity authorizes the read but NEVER becomes Graph credentials.
        app_request = replace(
            request, principal_id=self.app_service_principal_id,
            requester_kind="service",
        )
        invoked = self.delegate.invoke(request=app_request, resolution=resolution)
        return InvocationResult(
            output=dict(invoked.output),
            artifact_references=invoked.artifact_references,
            attempts=invoked.attempts,
            telemetry=invoked.telemetry,
            information_authorization=_information_policy(request.capability_name),
        )


def build_sharepoint_read_invoker(
    *, boundary_db: Path, state_db: Path, openbao_url: str,
    role_id_path: Path, secret_id_path: Path,
    tenant_id: str, transport: HttpTransport, audit: AuditSink,
    approved_owner_ids: frozenset[str],
    original_identity_bindings: TrustedPrincipalBindingResolver,
    expected_client_id: str = "client-aot-internal",
    expected_domain: str = "teamaot.com",
):
    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=boundary_db, openbao_url=openbao_url,
        role_id_path=role_id_path, secret_id_path=secret_id_path,
        transport=transport,
    )
    boundaries = SQLiteClientBoundaryRepository(runtime.store)
    require_validated_sharepoint_service_boundary(
        boundaries=boundaries, tenant_id=tenant_id,
        expected_client_id=expected_client_id, expected_domain=expected_domain,
    )
    record = boundaries.find_active_for_external_tenant(
        provider=SHAREPOINT_PROVIDER, external_tenant_id=tenant_id)
    if record is None or not record.service_principal_id:
        raise PermissionError("Dedicated app-only service principal unavailable")
    manager = build_sharepoint_site_management(
        runtime=runtime, tenant_id=tenant_id,
        state_db=state_db, transport=transport)
    connector = GovernedSharePointConnector(
        reader=runtime.reader, bindings=_NoClientBindings(),
        authorizer=AotSharePointSiteDocumentAuthorizer(
            site_access=manager.site_access,
            approved_service_principals=frozenset({record.service_principal_id}),
            content_release=_NoContentRelease(),
        ),
        audit=audit,
        organization_bindings=_ValidatedAotServiceBinding(
            principal_id=record.service_principal_id, tenant_id=tenant_id),
        site_access=manager.site_access,
    )
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={SHAREPOINT_PROVIDER: connector},
        provider_capability_map={(SHAREPOINT_PROVIDER, name): name
                                 for name in SHAREPOINT_CAPABILITIES},
    )
    return AotSharePointAuthorizingInvoker(
        delegate=invoker, approved_owner_ids=approved_owner_ids,
        original_identity_bindings=original_identity_bindings,
        app_service_principal_id=record.service_principal_id,
    )


def register_sharepoint_read_invokers(*, invokers: CapabilityInvokerRegistry,
                                     invoker: AotSharePointAuthorizingInvoker):
    for name in sorted(SHAREPOINT_CAPABILITIES):
        invokers.register(name, invoker)
