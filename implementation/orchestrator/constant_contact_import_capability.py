"""Unregistered, BUILDING-only governed Constant Contact import capability.

This definition is *not* added to production composition or MCP exposed actions.
It cannot execute until provider-backed acceptance, exact plan Teams approval,
account-binding and production release gates are separately satisfied.
"""
from __future__ import annotations

from datetime import datetime
from kernel.capabilities import (
    CapabilityApproval, CapabilityDefinition, CapabilityEvidence,
    CapabilityLifecycle, CapabilityRisk, CapabilityStewardship,
    IdempotencyBehavior,
)

MARKETING_CONTACT_IMPORT = "marketing.contact.import"


def import_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=MARKETING_CONTACT_IMPORT,
        version="1.0",
        display_name="Import Contacts Into Approved Constant Contact List",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Import consent-verified AOT Excel contacts into exact Constant "
            "Contact list IDs following fresh provider evidence and exact authenticated Owner approval."
        ),
        owner_service="Jason Contact Management",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal", "confidential"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/marketing-contact-import/1.0",
        output_schema_reference="schema://jason/marketing-contact-import-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "verified AOT requester identity",
                "original Excel content and consent evidence digest",
                "fresh OAuth-bound Constant Contact account and target list identity",
                "complete provider suppression checks for every target contact",
                "exact verified Owner approval for immutable import plan",
                "durable one-time claim and provider activity ID",
            ),
            verification_requirements=(
                "no implicit opt-in without documented consent",
                "provider activity is complete without errors",
                "each imported contact and intended list membership read back",
                "unknown activity/write outcomes are not redispatched",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve", "governance.action.evaluate"}),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior="Fail closed; no fallback writes, automatic redispatch, or unverified success.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Govern contact imports without bypassing native Teams approval",
            review_interval_days=30,
            retirement_criteria=("Constant Contact is no longer an approved AOT platform",),
            authoritative_change_sources=("Constant Contact V3 API and approval policies",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "marketing_contact",
            "operation": "import",
            "selector_keys": "list_ids,preview_digest,account_binding,consent_evidence",
            "approval_channel": "canonical_verified_owner",
            "live_enablement": "blocked_until_governed_provider_acceptance",
        },
    )
