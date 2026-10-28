"""Named, off-by-default runtime registrations for routine IT Glue and Entra RW.

Provider permissions and per-client JKD-001 grants are NOT created here.
Only an exact independently configured activation profile promotes a named
capability to ACTIVE; unconfigured changes stay source-only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from kernel.capabilities import (
    CapabilityApproval, CapabilityDefinition, CapabilityEvidence,
    CapabilityLifecycle, CapabilityRegistryService, CapabilityRisk,
    CapabilityStewardship, IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider, ExecutionProviderRegistryService,
    ProviderApproval, ProviderFeatures, ProviderHealth, ProviderLifecycle,
    ProviderLimits, ProviderStewardship, ProviderType,
)

IT_GLUE_NOTES = "documentation.configuration.update"
IT_GLUE_PROVIDER_ID = "it_glue_configuration_note_update"
ENTRA_USER_CREATE = "identity.user.create"
ENTRA_PROVIDER_ID = "microsoft_graph_standard_user_create"

IT_GLUE_PROFILE_ENV = "JASON_IT_GLUE_ROUTINE_RW_PROFILE"
IT_GLUE_PROFILE = "configuration-notes-v1"
ENTRA_PROFILE_ENV = "JASON_ENTRA_STANDARD_USER_CREATE_PROFILE"
ENTRA_PROFILE = "cloud-user-v1"


@dataclass(frozen=True, slots=True)
class RoutineRwActivation:
    enabled_capabilities: tuple[str, ...]
    enabled_providers: tuple[str, ...]
    blocked_capabilities: tuple[str, ...] = ()


def _capability(*, now: datetime, name: str, notes: bool) -> CapabilityDefinition:
    description = (
        "Change notes on one verified unrestricted IT Glue configuration"
        if notes else
        "Create one disabled cloud-only Entra user under an approved onboarding request"
    )
    return CapabilityDefinition(
        capability_name=name, version="1.0",
        display_name=("IT Glue Configuration Notes Update" if notes else
                      "Entra Standard Cloud User Create"),
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=description,
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=True, approver_classes=("technician", "owner"),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated authorized AOT human requester",
                "exact validated client and provider tenant/organization",
                "exact provider write plan and approved arguments",
                "provider mutation and independent post-write verification",
            ),
            verification_requirements=(
                "separate provider write credential with valid scope",
                "exact client boundary and positive user authorization",
                "no unrelated attributes or unintended privileges",
                "idempotency or duplicate detection before provider request",
                "verified post-mutation readback and auditable outcome",
            ),
        ),
        dependencies=frozenset({
            "identity.authorization.resolve", "governance.action.evaluate",
        }),
        idempotency_behavior=(
            IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT if notes
            else IdempotencyBehavior.NON_IDEMPOTENT
        ),
        idempotency_key_required=True,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior="Fail closed; never substitute read credentials, retry ambiguous writes, or claim unverified success.",
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=description,
            review_interval_days=30,
            retirement_criteria=(
                "Requester or client authorization cannot be verified.",
                "Provider capability is withdrawn or becomes unsafe.",
            ),
            authoritative_change_sources=(
                "IT Glue API documentation" if notes else "Microsoft Graph v1.0 documentation",
            ),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true", "read_only": "false",
            "write_capability": "true",
            "resource_types": (
                "documentation_configuration" if notes else "identity_user"
            ),
            "operation": "update" if notes else "create",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "requires_exact_client_grant": "true",
            "activation_state": "source_only_unconfigured",
        },
    )


def _provider(*, now: datetime, provider_id: str, name: str) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=("IT Glue Configuration Notes Update" if name == IT_GLUE_NOTES
                      else "Microsoft Graph Standard User Create"),
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({name}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=6,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Separate bounded, customer-scoped governed provider write.",
            review_interval_days=30, last_reviewed_at=now,
            retirement_criteria=(
                "Positive requester/client source authorization fails.",
                "Provider-only credential boundaries cannot be maintained.",
            ),
            vendor_change_sources=("Official provider API documentation",),
            operational_owner="AOT IT Operations", approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "write_capability": "true",
            "mutation_scope": "single_resource_only",
            "activation_state": "source_only_unconfigured",
        },
    )


def register_routine_rw_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    bootstrap_present: Callable[[str], bool] | None = None,
) -> RoutineRwActivation:
    enabled_caps = []
    enabled_providers = []
    blocked = []
    for name, provider_id, profile_env, profile, notes in (
        (IT_GLUE_NOTES, IT_GLUE_PROVIDER_ID, IT_GLUE_PROFILE_ENV, IT_GLUE_PROFILE, True),
        (ENTRA_USER_CREATE, ENTRA_PROVIDER_ID, ENTRA_PROFILE_ENV, ENTRA_PROFILE, False),
    ):
        capabilities.register(_capability(now=now, name=name, notes=notes))
        providers.register(_provider(now=now, provider_id=provider_id, name=name))
        if os.getenv(profile_env, "").strip().casefold() != profile:
            continue
        if bootstrap_present is None or not bootstrap_present(name):
            blocked.append(name)
            continue
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
        providers.set_approval(
            provider_id=provider_id,
            approval_status=ProviderApproval.APPROVED,
        )
        providers.set_health(
            provider_id=provider_id,
            health_status=ProviderHealth.HEALTHY,
        )
        providers.set_lifecycle(
            provider_id=provider_id,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
        )
        enabled_caps.append(name)
        enabled_providers.append(provider_id)
    return RoutineRwActivation(
        enabled_capabilities=tuple(enabled_caps),
        enabled_providers=tuple(enabled_providers),
        blocked_capabilities=tuple(blocked),
    )
