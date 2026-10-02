from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

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
from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode
from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationRequest
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import InvocationResult
from autonomous_remediation.autonomous_principal import AutonomousPrincipal, AutonomousRequestFactory
from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger

from .teams_gateway_transport import TeamsGatewayPreparedRequest, TeamsGatewayTransport


CAPABILITY = "communication.teams.autonomy.completion.send"
PROVIDER = "microsoft_teams_gateway_autonomy_completion"
PROFILE_ENV = "JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE"
PROFILE = "person-al-v1"
RECIPIENT_JASON_IDENTITY = "person-al"

EXECUTE_GRANT_ID = "grant-jason-autonomy-worker-teams-autonomy-completion-v1"

_ALLOWED_EVENTS = frozenset(
    {
        "patch_completed",
        "deployment_completed",
        "support_item_resolved",
        "self_heal_escalation",
    }
)


class AutonomousCompletionNotificationActivationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _PreparedNotification:
    request: TeamsGatewayPreparedRequest


def enabled() -> bool:
    return os.getenv(PROFILE_ENV, "").strip().casefold() == PROFILE


def _capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=CAPABILITY,
        version="1.0",
        display_name="Send Autonomous Completion Notification",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Notify the AOT owner in Teams only after Jason independently verifies "
            "an autonomous patch, deployment, or support-item resolution."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/autonomy-completion-notification/1.0",
        output_schema_reference="schema://jason/autonomy-completion-notification-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "verified autonomous terminal event",
                "fixed recipient Jason identity",
                "bounded event identifiers",
            ),
            verification_requirements=(
                "recipient resolves from active person-al Teams binding",
                "exactly one proactive Teams send attempt",
                "provider returns message id",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve"}),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without recipient substitution; notification failure never "
            "changes the underlying patch, deployment, support, or ticket result."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Give the AOT owner concise evidence-backed notice when Jason completes "
                "autonomous production work."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Owner no longer wants autonomous completion notifications.",
                "Teams gateway is replaced by a stronger governed notification channel.",
            ),
            authoritative_change_sources=(
                "J-CHANGE-002",
                "Jason Development & Release Coordinator",
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
            "resource_types": "communication_message,microsoft_teams",
            "operation": "send_autonomous_completion",
            "fixed_recipient_identity": RECIPIENT_JASON_IDENTITY,
            "mcp_action_enabled": "false",
            "autonomous_only": "true",
        },
    )


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PROVIDER,
        display_name="Jason Teams Gateway Autonomous Completion",
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
            maximum_requests_per_minute=10,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Reuse the existing Teams gateway with a fixed recipient and bounded "
                "completion-message contract."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Teams completion notification channel is retired.",),
            vendor_change_sources=("Microsoft Agents SDK",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={"write_capability": "true", "fixed_recipient": "person-al"},
    )


def register_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> bool:
    capabilities.register(_capability(now))
    providers.register(_provider(now))
    profile = os.getenv(PROFILE_ENV, "").strip().casefold()
    if not profile:
        return False
    if profile != PROFILE:
        raise AutonomousCompletionNotificationActivationError(
            "unsupported autonomous completion Teams profile"
        )
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
    worker = IdentityRecord(
        identity_id="jason-autonomy-worker",
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    current = identity_authority.identities.get(worker.identity_id)
    if current is None:
        identity_authority.identities.put(worker)
    elif current != worker:
        raise AutonomousCompletionNotificationActivationError(
            "autonomous worker identity conflicts with existing JKD-001 record"
        )

    grant = AuthorityGrant(
        grant_id=EXECUTE_GRANT_ID,
        subject_id=worker.identity_id,
        capability=CAPABILITY,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.EXECUTE,
        approval_required=False,
        status="active",
    )
    existing = identity_authority.grants.get(grant.grant_id)
    if existing is None:
        identity_authority.grants.put(grant)
        return (grant.grant_id,)
    if existing != grant:
        raise AutonomousCompletionNotificationActivationError(
            "autonomous completion notification grant conflicts with existing JKD-001 record"
        )
    return ()


def _bounded(value: Any, field: str, maximum: int = 300) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty and at most {maximum} characters")
    return text


def _render(arguments: Mapping[str, Any]) -> tuple[str, str]:
    allowed = {
        "event_type",
        "candidate_sha",
        "support_item",
        "ticket_number",
        "hostname",
        "patch_summary",
        "resolution_summary",
        "degraded_function",
        "evidence_summary",
        "attempt_summary",
        "owner_action",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(
            "unsupported autonomous completion notification arguments: "
            + ", ".join(sorted(str(value) for value in unknown))
        )
    event = str(arguments.get("event_type") or "").strip().casefold()
    if event not in _ALLOWED_EVENTS:
        raise ValueError("unsupported autonomous completion event_type")

    if event == "deployment_completed":
        candidate = _bounded(arguments.get("candidate_sha"), "candidate_sha", 40)
        support = _bounded(arguments.get("support_item"), "support_item", 80)
        if len(candidate) != 40:
            raise ValueError("candidate_sha must be exact")
        text = (
            "Jason autonomous deployment completed successfully. "
            f"Support item {support}; live revision {candidate[:12]}… verified healthy."
        )
        return event, text

    if event == "self_heal_escalation":
        degraded = _bounded(arguments.get("degraded_function"), "degraded_function", 160)
        evidence = _bounded(arguments.get("evidence_summary"), "evidence_summary", 400)
        attempts = _bounded(arguments.get("attempt_summary"), "attempt_summary", 400)
        owner_action = _bounded(arguments.get("owner_action"), "owner_action", 300)
        text = (
            "Jason needs owner action to restore full functionality. "
            f"Degraded function: {degraded}. Evidence: {evidence}. "
            f"Recovery attempted: {attempts}. Owner action required: {owner_action}."
        )
        return event, text

    if event == "patch_completed":
        ticket = _bounded(arguments.get("ticket_number"), "ticket_number", 80)
        hostname = _bounded(arguments.get("hostname"), "hostname", 120)
        patch = _bounded(arguments.get("patch_summary"), "patch_summary", 300)
        text = (
            "Jason autonomous patch work completed successfully. "
            f"Ticket {ticket}; device {hostname}; verified patch state: {patch}."
        )
        return event, text

    support = _bounded(arguments.get("support_item"), "support_item", 80)
    detail = _bounded(arguments.get("resolution_summary"), "resolution_summary", 300)
    text = (
        f"Jason autonomously resolved support item {support}. "
        f"Verified resolution: {detail}."
    )
    return event, text


@dataclass(slots=True)
class AutonomousCompletionTeamsInvoker:
    gateway_url: str
    token_file: Path
    bindings: Any

    def _prepare(self, *, request: OrchestrationRequest, resolution: CapabilityResolutionResult):
        if request.capability_name != CAPABILITY:
            raise PermissionError("autonomous completion capability mismatch")
        if resolution.selected_provider_id != PROVIDER:
            raise PermissionError("autonomous completion provider mismatch")
        if request.principal_id != "jason-autonomy-worker":
            raise PermissionError("autonomous completion notifications require Jason autonomy workload")
        if request.permission_mode != "execute":
            raise PermissionError("autonomous completion notification requires execute permission")

        event, text = _render(dict(request.arguments or {}))
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=RECIPIENT_JASON_IDENTITY
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError("person-al Teams identity binding unavailable")
        tenant = str(binding.microsoft_tenant_id).strip()
        aad = str(binding.microsoft_object_id).strip()
        if not tenant or not aad:
            raise PermissionError("person-al Teams binding is incomplete")
        payload = {
            "aadObjectId": aad,
            "tenantId": tenant,
            "text": text,
        }
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
            material_parameters={"event_type": event},
            symbolic_resolutions={"recipient_jason_identity": RECIPIENT_JASON_IDENTITY},
        )
        return PreparedExecutionPlan(
            plan=plan,
            opaque=_PreparedNotification(
                request=TeamsGatewayTransport(
                    gateway_url=self.gateway_url,
                    token_file=self.token_file,
                ).prepare(payload),
            ),
        )

    def prepare_execution_plan(self, *, request, resolution):
        return self._prepare(request=request, resolution=resolution)

    def invoke_execution_plan(self, *, request, resolution, prepared):
        expected = self._prepare(request=request, resolution=resolution)
        if prepared.plan.fingerprint != expected.plan.fingerprint:
            raise PermissionError("autonomous completion execution plan changed")
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedNotification):
            raise PermissionError("invalid autonomous completion prepared state")
        result = TeamsGatewayTransport(
            gateway_url=self.gateway_url,
            token_file=self.token_file,
        ).send(opaque.request)
        if result.get("status") != "succeeded" or not result.get("message_id"):
            raise RuntimeError("autonomous completion Teams send failed")
        return InvocationResult(
            output={
                "provider": PROVIDER,
                "channel": "microsoft_teams",
                "recipient_identity": RECIPIENT_JASON_IDENTITY,
                "message_id": str(result["message_id"]),
            },
            attempts=1,
        )

    def invoke(self, *, request, resolution):
        prepared = self.prepare_execution_plan(request=request, resolution=resolution)
        return self.invoke_execution_plan(
            request=request,
            resolution=resolution,
            prepared=prepared,
        )


def build_invoker(*, bindings) -> AutonomousCompletionTeamsInvoker:
    return AutonomousCompletionTeamsInvoker(
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
    invoker: AutonomousCompletionTeamsInvoker,
) -> None:
    invokers.register(CAPABILITY, invoker)


@dataclass(slots=True)
class GovernedAutonomousCompletionNotifier:
    request_factory: AutonomousRequestFactory
    orchestrator: Any

    def send(self, event_type: str, **arguments: Any) -> Mapping[str, Any]:
        request = self.request_factory.build(
            capability_name=CAPABILITY,
            arguments={"event_type": event_type, **arguments},
            client_id=None,
            standing_policy=None,
            correlation_id=None,
        )
        result = self.orchestrator.execute(request)
        status = getattr(getattr(result, "status", None), "value", "")
        if status != "succeeded":
            raise RuntimeError(
                "autonomous completion Teams notification failed: "
                + str(
                    getattr(result, "error_code", None)
                    or getattr(result, "reason_codes", ())
                    or status
                )
            )
        output = getattr(result, "output", None)
        return dict(output) if isinstance(output, Mapping) else {}


def build_notifier(
    *,
    enabled: bool,
    identity_authority,
    capabilities,
    approvals,
    execution_ledger: SQLiteGovernedExecutionLedger,
    orchestrator,
    promotion_db: Path,
):
    if not enabled:
        return None
    request_factory = AutonomousRequestFactory(
        principal=AutonomousPrincipal(),
        authority=identity_authority,
        capabilities=capabilities,
        approvals=approvals,
        execution_ledger=execution_ledger,
        promotion_store=SQLitePlaybookAutonomyApprovalStore(promotion_db),
    )
    return GovernedAutonomousCompletionNotifier(
        request_factory=request_factory,
        orchestrator=orchestrator,
    )


@dataclass(slots=True)
class AutonomousDeploymentCompletionNotificationMaintenance:
    notifier: GovernedAutonomousCompletionNotifier
    spool_root: Path = Path("/var/lib/jason/openclaw/autonomous-repair")
    interval_seconds: int = 60
    now: Any = None
    _next_due_at: Any = None

    def __post_init__(self) -> None:
        if self.interval_seconds < 30:
            raise ValueError("notification maintenance interval must be at least 30 seconds")
        if self.now is None:
            from datetime import datetime, timezone
            self.now = lambda: datetime.now(timezone.utc)

    def tick(self) -> bool:
        from datetime import timedelta
        current = self.now()
        if self._next_due_at is not None and current < self._next_due_at:
            return False
        self._next_due_at = current + timedelta(seconds=self.interval_seconds)

        results = self.spool_root / "results"
        notified = self.spool_root / "notifications"
        if not results.exists():
            return False
        notified.mkdir(parents=True, exist_ok=True, mode=0o700)

        handled = False
        for path in sorted(results.glob("*.json"), key=lambda item: item.stat().st_mtime):
            marker = notified / path.name
            if marker.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if (
                payload.get("state") != "succeeded"
                or payload.get("verification_passed") is not True
                or str(payload.get("candidate_sha") or "").strip()
                != str(payload.get("live_revision") or "").strip()
            ):
                continue
            candidate = str(payload.get("candidate_sha") or "").strip().casefold()
            support_item = str(payload.get("support_item") or "").strip().upper()
            if len(candidate) != 40 or not support_item:
                continue

            self.notifier.send(
                "deployment_completed",
                candidate_sha=candidate,
                support_item=support_item,
            )
            temp = marker.with_suffix(marker.suffix + ".tmp")
            temp.write_text(
                json.dumps(
                    {
                        "event_type": "deployment_completed",
                        "candidate_sha": candidate,
                        "support_item": support_item,
                        "notified_at": current.isoformat(),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(temp, 0o600)
            os.replace(temp, marker)
            handled = True
        return handled


def build_deployment_notification_maintenance(
    *,
    notifier: GovernedAutonomousCompletionNotifier | None,
    spool_root: Path = Path("/var/lib/jason/openclaw/autonomous-repair"),
):
    if notifier is None:
        return None
    return AutonomousDeploymentCompletionNotificationMaintenance(
        notifier=notifier,
        spool_root=spool_root,
    )


@dataclass(slots=True)
class SelfHealEscalationNotificationMaintenance:
    notifier: GovernedAutonomousCompletionNotifier
    spool_root: Path = Path("/var/lib/jason/openclaw/self-heal")
    interval_seconds: int = 60
    now: Any = None
    _next_due_at: Any = None

    def __post_init__(self) -> None:
        if self.interval_seconds < 30:
            raise ValueError("self-heal notification interval must be at least 30 seconds")
        if self.now is None:
            from datetime import datetime, timezone
            self.now = lambda: datetime.now(timezone.utc)

    def tick(self) -> bool:
        from datetime import timedelta
        current = self.now()
        if self._next_due_at is not None and current < self._next_due_at:
            return False
        self._next_due_at = current + timedelta(seconds=self.interval_seconds)

        escalations = self.spool_root / "escalations"
        notified = self.spool_root / "notifications"
        if not escalations.exists():
            return False
        notified.mkdir(parents=True, exist_ok=True, mode=0o700)

        handled = False
        for path in sorted(escalations.glob("*.json"), key=lambda item: item.stat().st_mtime):
            marker = notified / path.name
            if marker.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if payload.get("state") != "owner_action_required":
                continue
            fingerprint = str(payload.get("fingerprint") or "").strip()
            if not fingerprint or path.stem != fingerprint:
                continue
            self.notifier.send(
                "self_heal_escalation",
                degraded_function=str(payload.get("degraded_function") or ""),
                evidence_summary=str(payload.get("evidence_summary") or ""),
                attempt_summary=str(payload.get("attempt_summary") or ""),
                owner_action=str(payload.get("owner_action") or ""),
            )
            temp = marker.with_suffix(marker.suffix + ".tmp")
            temp.write_text(
                json.dumps(
                    {
                        "event_type": "self_heal_escalation",
                        "fingerprint": fingerprint,
                        "notified_at": current.isoformat(),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            os.chmod(temp, 0o600)
            os.replace(temp, marker)
            handled = True
        return handled


def build_self_heal_escalation_notification_maintenance(
    *,
    notifier: GovernedAutonomousCompletionNotifier | None,
    spool_root: Path = Path("/var/lib/jason/openclaw/self-heal"),
):
    if notifier is None:
        return None
    return SelfHealEscalationNotificationMaintenance(
        notifier=notifier,
        spool_root=spool_root,
    )
