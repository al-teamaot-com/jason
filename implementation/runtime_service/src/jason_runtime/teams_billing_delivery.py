"""Governed Microsoft Teams capability for procurement billing notifications.

The billing reconciliation workflow decides *when* a notification is required.
This module owns the canonical notification operation, exact workload authority,
recipient binding validation, execution-plan binding, and Teams provider adapter.
The underlying gateway transport is shared with other Teams capabilities.

Different Teams capabilities intentionally retain different authority semantics.
This capability does not weaken or inherit the owner-approval rules of the generic
interactive Teams-send capability.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.identity_authority import (
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityRecord,
    PermissionMode,
)
from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import InvocationResult

from .autotask_procurement import (
    AUTOTASK_PROCUREMENT_PROFILE,
    AUTOTASK_PROCUREMENT_PROFILE_ENV,
)
from .procurement_web_read import PROFILE as PROCUREMENT_WEB_READ_PROFILE
from .procurement_web_read import PROFILE_ENV as PROCUREMENT_WEB_READ_PROFILE_ENV
from .teams_gateway_transport import TeamsGatewayPreparedRequest, TeamsGatewayTransport


CAPABILITY = "communication.teams.billing.notification.send"
PROVIDER = "microsoft_teams_gateway_billing_notification"
AUDIT_WORKER_ID = "jason-procurement-billing-audit"
POLICY_ID = "aot-procurement-billing-notification-v1"
EXECUTE_GRANT_ID = "grant-procurement-billing-audit-teams-notification-v1"
LORI_EMAIL = "lori@teamaot.com"

_ALLOWED_KINDS = frozenset({"technician_disposition", "lori_escalation"})


class BillingNotificationActivationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _PreparedBillingNotification:
    request: TeamsGatewayPreparedRequest


def enabled() -> bool:
    return (
        os.getenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, "").strip().casefold()
        == AUTOTASK_PROCUREMENT_PROFILE
        and os.getenv(PROCUREMENT_WEB_READ_PROFILE_ENV, "").strip().casefold()
        == PROCUREMENT_WEB_READ_PROFILE
    )


def _capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=CAPABILITY,
        version="1.0",
        display_name="Send Procurement Billing Notification",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Send a bounded Teams notification produced by the procurement billing "
            "reconciliation workflow to the exact active AOT identity selected from "
            "authoritative ticket/resource evidence or the configured Lori escalation target."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/communication-teams-billing-notification-send/1.0",
        output_schema_reference=(
            "schema://jason/communication-teams-billing-notification-send-result/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "exact procurement billing-audit workload identity",
                "active AOT Microsoft identity binding",
                "bounded billing notification kind",
                "billing evidence key",
            ),
            verification_requirements=(
                "recipient resolves from active Jason-to-Microsoft identity binding",
                "provider target and content are bound before execution",
                "exactly one provider send attempt",
                "provider returns a message identifier",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve"}),
        idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without recipient substitution, caller escalation to generic "
            "Teams authority, or provider retry."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Move scheduled billing notifications through the same governed "
                "capability/orchestrator model used by other Jason operations."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Procurement billing notification workflow is retired.",
                "A stronger common communication policy model safely subsumes this contract.",
            ),
            authoritative_change_sources=(
                "Project Jason procurement billing workflow",
                "Microsoft Teams gateway contract",
            ),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "communication_message,microsoft_teams,billing_audit",
            "operation": "send_billing_notification",
            "service_principal_only": "true",
            "mcp_action_enabled": "false",
            "allowed_notification_kinds": ",".join(sorted(_ALLOWED_KINDS)),
        },
    )


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PROVIDER,
        display_name="Jason Teams Gateway Billing Notification",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({CAPABILITY}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=20,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Reuse the shared Teams gateway transport behind a billing-specific "
                "governed capability."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Billing notification capability is retired or safely subsumed.",
            ),
            vendor_change_sources=("Microsoft Teams gateway contract",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "write_capability": "true",
            "shared_transport": "teams_gateway_transport",
            "billing_notification_only": "true",
        },
    )


def register_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> bool:
    capabilities.register(_capability(now))
    providers.register(_provider(now))
    if not enabled():
        return False

    capabilities.set_lifecycle(
        capability_name=CAPABILITY,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return True


def ensure_authority(identity_authority) -> tuple[str, ...]:
    if not enabled():
        return ()

    expected_identity = IdentityRecord(
        identity_id=AUDIT_WORKER_ID,
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    current_identity = identity_authority.identities.get(AUDIT_WORKER_ID)
    if current_identity is None:
        identity_authority.identities.put(expected_identity)
    elif current_identity != expected_identity:
        raise BillingNotificationActivationError(
            "procurement billing notification identity conflicts with JKD-001"
        )

    grant = AuthorityGrant(
        grant_id=EXECUTE_GRANT_ID,
        subject_id=AUDIT_WORKER_ID,
        capability=CAPABILITY,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.EXECUTE,
        approval_required=False,
        status="active",
    )
    current = identity_authority.grants.get(grant.grant_id)
    if current is None:
        identity_authority.grants.put(grant)
        return (grant.grant_id,)
    if current != grant:
        raise BillingNotificationActivationError(
            "procurement billing notification grant conflicts with JKD-001"
        )
    return ()


def _bounded_text(value: Any, field: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty and at most {maximum} characters")
    return text


@dataclass(slots=True)
class BillingNotificationTeamsInvoker:
    gateway_url: str
    token_file: Path
    bindings: Any

    def _prepare(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> PreparedExecutionPlan:
        if request.capability_name != CAPABILITY:
            raise PermissionError("billing notification capability mismatch")
        if resolution.selected_provider_id != PROVIDER:
            raise PermissionError("billing notification provider mismatch")
        if request.principal_id != AUDIT_WORKER_ID:
            raise PermissionError(
                "billing notification requires the procurement billing-audit workload"
            )
        if request.organization_id != "aot" or request.client_id is not None:
            raise PermissionError("billing notification scope must be AOT organization-only")
        if request.permission_mode != "execute":
            raise PermissionError("billing notification requires execute permission")

        arguments = dict(request.arguments or {})
        allowed = {
            "notification_kind",
            "recipient_identity_id",
            "text",
            "card",
            "evidence_key",
        }
        unknown = set(arguments) - allowed
        if unknown:
            raise ValueError(
                "unsupported billing notification arguments: "
                + ", ".join(sorted(str(value) for value in unknown))
            )

        kind = _bounded_text(
            arguments.get("notification_kind"),
            "notification_kind",
            80,
        ).casefold()
        if kind not in _ALLOWED_KINDS:
            raise ValueError("unsupported billing notification kind")

        recipient_identity = _bounded_text(
            arguments.get("recipient_identity_id"),
            "recipient_identity_id",
            160,
        )
        text = _bounded_text(arguments.get("text"), "text", 4000)
        evidence_key = _bounded_text(
            arguments.get("evidence_key"),
            "evidence_key",
            300,
        )
        card = arguments.get("card")
        if kind == "technician_disposition":
            if not isinstance(card, Mapping) or card.get("type") != "AdaptiveCard":
                raise ValueError(
                    "technician_disposition requires one AdaptiveCard payload"
                )
            normalized_card: dict[str, Any] | None = dict(card)
        else:
            if card is not None:
                raise ValueError("lori_escalation does not accept an AdaptiveCard")
            normalized_card = None

        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=recipient_identity
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError("billing notification Teams binding unavailable")

        tenant = _bounded_text(
            getattr(binding, "microsoft_tenant_id", ""),
            "microsoft_tenant_id",
            160,
        )
        aad = _bounded_text(
            getattr(binding, "microsoft_object_id", ""),
            "microsoft_object_id",
            160,
        )
        payload: dict[str, Any] = {
            "aadObjectId": aad,
            "tenantId": tenant,
            "text": text,
        }
        if normalized_card is not None:
            payload["card"] = normalized_card

        plan = ExecutionPlan(
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=None,
            canonical_capability=CAPABILITY,
            selected_provider_id=PROVIDER,
            provider_capability=CAPABILITY,
            action_method="POST",
            resource_type="microsoft_teams_conversation",
            resource_identifier=f"{tenant}:{aad}",
            normalized_path="/internal/proactive/send",
            normalized_payload=payload,
            material_parameters={
                "notification_kind": kind,
                "evidence_key": evidence_key,
            },
            symbolic_resolutions={
                "recipient_jason_identity": recipient_identity,
            },
        )
        transport = TeamsGatewayTransport(
            gateway_url=self.gateway_url,
            token_file=self.token_file,
        )
        return PreparedExecutionPlan(
            plan=plan,
            opaque=_PreparedBillingNotification(
                request=transport.prepare(payload),
            ),
        )

    def prepare_execution_plan(self, *, request, resolution):
        return self._prepare(request=request, resolution=resolution)

    def invoke_execution_plan(self, *, request, resolution, prepared):
        expected = self._prepare(request=request, resolution=resolution)
        if prepared.plan.fingerprint != expected.plan.fingerprint:
            raise PermissionError("billing notification execution plan changed")
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedBillingNotification):
            raise PermissionError("invalid billing notification prepared state")
        result = TeamsGatewayTransport(
            gateway_url=self.gateway_url,
            token_file=self.token_file,
        ).send(opaque.request)
        if result.get("status") != "succeeded" or not result.get("message_id"):
            raise RuntimeError("Teams billing notification delivery failed")
        return InvocationResult(
            output={
                "provider": PROVIDER,
                "provider_capability": CAPABILITY,
                "channel": "microsoft_teams",
                "recipient_identity": str(
                    prepared.plan.symbolic_resolutions["recipient_jason_identity"]
                ),
                "message_id": str(result["message_id"]),
                "evidence_key": str(
                    prepared.plan.material_parameters["evidence_key"]
                ),
            },
            attempts=1,
        )

    def invoke(self, *, request, resolution):
        prepared = self.prepare_execution_plan(
            request=request,
            resolution=resolution,
        )
        return self.invoke_execution_plan(
            request=request,
            resolution=resolution,
            prepared=prepared,
        )


def build_invoker(*, bindings) -> BillingNotificationTeamsInvoker:
    return BillingNotificationTeamsInvoker(
        gateway_url=os.getenv(
            "JASON_TEAMS_GATEWAY_INTERNAL_URL",
            "http://jason-teams-gateway:3979",
        ),
        token_file=Path(
            os.getenv(
                "JASON_TEAMS_PROACTIVE_TOKEN_FILE",
                "/run/jason-secrets/teams-proactive/token",
            )
        ),
        bindings=bindings,
    )


def register_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: BillingNotificationTeamsInvoker,
) -> None:
    invokers.register(CAPABILITY, invoker)


@dataclass(slots=True)
class GovernedBillingAuditNotificationPort:
    authority: Any
    capabilities: CapabilityRegistryService
    orchestrator: Any
    bindings: Any
    lori_email: str = LORI_EMAIL

    def identity_for_email(self, *, email_address: str) -> str | None:
        binding = self.bindings.find_active_by_email(email_address=email_address)
        if binding is None or getattr(binding, "status", None) != "active":
            return None
        identity_id = str(
            getattr(binding, "jason_identity_id", "") or ""
        ).strip()
        return identity_id or None

    def _send(
        self,
        *,
        notification_kind: str,
        recipient_identity_id: str,
        text: str,
        evidence_key: str,
        card: Mapping[str, Any] | None = None,
    ) -> str:
        capability = self.capabilities.get_current(
            capability_name=CAPABILITY,
            allow_pilot=False,
        )
        execution_id = "exec_billing_notify_" + uuid4().hex
        correlation_id = "corr_billing_notify_" + uuid4().hex
        decision = self.authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation_id,
                principal_id=AUDIT_WORKER_ID,
                organization_id="aot",
                client_id=None,
                capability=CAPABILITY,
                requested_mode=PermissionMode.EXECUTE,
                authentication_assurance="workload_identity",
            )
        )
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise PermissionError(
                "billing notification authority denied: "
                + ",".join(decision.reason_codes)
            )
        if decision.execution_context is None:
            raise PermissionError("billing notification authority context missing")
        if capability.approval.required:
            raise PermissionError(
                "billing notification capability unexpectedly requires approval"
            )

        arguments: dict[str, Any] = {
            "notification_kind": notification_kind,
            "recipient_identity_id": recipient_identity_id,
            "text": text,
            "evidence_key": evidence_key,
        }
        if card is not None:
            arguments["card"] = dict(card)

        request = OrchestrationRequest(
            execution_id=execution_id,
            correlation_id=correlation_id,
            principal_id=AUDIT_WORKER_ID,
            organization_id="aot",
            client_id=None,
            capability_name=CAPABILITY,
            capability_version=capability.version,
            requested_mode="deterministic",
            permission_mode="execute",
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=False,
            risk=capability.risk_level.value,
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=False,
                retention_allowed=False,
            ),
            budget=ExecutionBudget(
                maximum_estimated_cost=Decimal("1.00"),
                maximum_attempts=1,
            ),
            arguments=arguments,
            requester_kind="service",
            principal_attributes={"workload": AUDIT_WORKER_ID},
            policy_ids=(POLICY_ID,),
            authority_context_id=decision.execution_context.context_id,
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise RuntimeError(
                "billing notification failed: "
                + str(
                    result.error_code
                    or ",".join(result.reason_codes)
                    or result.status.value
                )
            )
        message_id = str((result.output or {}).get("message_id") or "").strip()
        if not message_id:
            raise RuntimeError("billing notification returned no message identifier")
        return message_id

    def technician(
        self,
        *,
        jason_identity_id: str,
        text: str,
        card: Mapping[str, Any],
        evidence_key: str,
    ) -> str:
        return self._send(
            notification_kind="technician_disposition",
            recipient_identity_id=jason_identity_id,
            text=text,
            card=card,
            evidence_key=evidence_key,
        )

    def lori(self, *, text: str, evidence_key: str) -> str:
        recipient = self.identity_for_email(email_address=self.lori_email)
        if recipient is None:
            raise LookupError("Lori Teams binding unavailable")
        return self._send(
            notification_kind="lori_escalation",
            recipient_identity_id=recipient,
            text=text,
            evidence_key=evidence_key,
        )
