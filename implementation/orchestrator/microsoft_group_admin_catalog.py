"""Dormant, reusable governed Microsoft 365 group administration capabilities.

Not registered by production composition. Microsoft tenant administration
requires separately authorized app identities and exact-action approval.
"""
from __future__ import annotations

from datetime import datetime

from connectors.microsoft_graph.governed_operations import MICROSOFT_GOVERNED_OPERATIONS
from kernel.capabilities import (
    CapabilityApproval, CapabilityDefinition, CapabilityEvidence,
    CapabilityLifecycle, CapabilityRisk, CapabilityStewardship,
    IdempotencyBehavior,
)


def microsoft_group_admin_capabilities(*, now: datetime) -> tuple[CapabilityDefinition, ...]:
    definitions: list[CapabilityDefinition] = []
    details = {
        "identity.group.create": ("Create Assigned Microsoft 365 Group",
                                  "Create a standard owned security or Microsoft 365 group.",
                                  "create", IdempotencyBehavior.NON_IDEMPOTENT),
        "identity.group.member.add": ("Add Microsoft 365 Group Member",
                                      "Add one verified active user to a standard managed group.",
                                      "update", IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT),
    }
    if set(details) != set(MICROSOFT_GOVERNED_OPERATIONS):
        raise ValueError("Group capability definitions must match the registered operation catalog")

    for name, (display, purpose, verb, idempotency) in details.items():
        definitions.append(CapabilityDefinition(
            capability_name=name,
            version="1.0",
            display_name=display,
            lifecycle_status=CapabilityLifecycle.BUILDING,
            business_purpose=purpose,
            owner_service="Jason Governed Microsoft Administration",
            architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
            risk_level=CapabilityRisk.HIGH,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({"deterministic"}),
            input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
            output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
            invoking_roles=frozenset({"orchestrator"}),
            approval=CapabilityApproval(required=True, approver_classes=("owner", "administrator")),
            evidence=CapabilityEvidence(
                required=True,
                requirements=(
                    "authenticated technician with exact client entitlement",
                    "validated tenant-specific, separately consented Microsoft read/write app identities",
                    "exact approved intent and unmodified central execution plan",
                    "pre-action user/group identity and group policy",
                    "one provider POST and separate read-only readback",
                ),
                verification_requirements=(
                    "tenant, client, provider application, and profile remain verified",
                    "role-assignable, dynamic, synchronized and unsupported groups denied",
                    "exact owner or direct membership readback from same tenant",
                    "no blind retry on unknown Graph write outcomes",
                ),
            ),
            dependencies=frozenset({"identity.authorization.resolve", "governance.action.evaluate"}),
            idempotency_behavior=idempotency,
            idempotency_key_required=True,
            timeout_seconds=60,
            maximum_attempts=1,
            failure_behavior="Fail closed on identity, authorization, consent or incomplete readback; no auto-rePOST.",
            tenant_isolation_required=True,
            client_isolation_required=True,
            stewardship=CapabilityStewardship(
                steward="Microsoft Platform Steward",
                business_justification="Reused governed Microsoft Graph group administration for AOT managed clients.",
                review_interval_days=30,
                retirement_criteria=("Microsoft group permission grants cannot be verified.",
                                     "A safer separately scoped provider capability supersedes this implementation."),
                last_reviewed_at=now,
                operational_owner="AOT IT Operations",
                approval_owner="AOT Owner",
                authoritative_change_sources=("Microsoft Graph v1.0 group API",),
            ),
            created_at=now,
            metadata={
                "provider_neutral": "true",
                "provider": "microsoft_graph_group_write",
                "permission_profile": "group-write",
                "resource_types": "identity_group",
                "operation": verb,
                "read_only": "false",
                "write_capability": "true",
                "activation_state": "source_only_not_registered",
                "mcp_action_enabled": "false",
                "principal_authority": "bound_authentication_plus_client_entitlement",
                "exact_action_plan_required": "true",
                "customer_tenant_consent_required": "true",
            },
        ))
    return tuple(definitions)
