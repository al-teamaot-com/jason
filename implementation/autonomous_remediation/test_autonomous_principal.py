from datetime import datetime, timezone

import pytest

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)
from kernel.identity_authority import (
    AuthorityGrant,
    IdentityAuthorityService,
    IdentityRecord,
    PermissionMode,
)
from kernel.identity_authority.repositories import (
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
)
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger

from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore

from .autonomous_principal import (
    AutonomousAuthorityError,
    AutonomousPrincipal,
    AutonomousRequestFactory,
    StandingPolicyAuthorization,
)


def capability(*, approval_required=True):
    return CapabilityDefinition(
        capability_name="service.ticket.update",
        version="1.0",
        display_name="Ticket Update",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose="test",
        owner_service="test",
        architectural_capability_ids=frozenset({"JAC-005"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://test/in",
        output_schema_reference="schema://test/out",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=approval_required, approver_classes=("owner",) if approval_required else ()),
        evidence=CapabilityEvidence(required=True, requirements=("test",), verification_requirements=("test",)),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior="fail closed",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="test",
            business_justification="test",
            review_interval_days=30,
            retirement_criteria=("test",),
        ),
        created_at=datetime.now(timezone.utc),
    )


def build(tmp_path, *, with_grant=True, approval_required=True):
    identities = InMemoryIdentityRepository()
    grants = InMemoryAuthorityGrantRepository()
    approvals = InMemoryApprovalRepository()
    identities.put(IdentityRecord("jason-autonomy-worker", "service", "aot"))
    if with_grant:
        grants.put(AuthorityGrant(
            grant_id="grant-autonomy-ticket-update",
            subject_id="jason-autonomy-worker",
            capability="service.ticket.update",
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.EXECUTE,
            approval_required=approval_required,
        ))
    authority = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
        contexts=None,
    )
    registry = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    registry.register(capability(approval_required=approval_required))
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "governed.sqlite3"))
    ledger.initialize()
    promotion_store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "playbook-approvals.sqlite3")
    promotion = promotion_store.new(playbook_id="unexpected-shutdown", playbook_version="1.0.0", policy_id="approved-autonomous-playbook", allowed_capabilities=["service.ticket.update"], approved_by="person-al")
    promotion_store.put(promotion)
    factory = AutonomousRequestFactory(
        principal=AutonomousPrincipal(),
        authority=authority,
        capabilities=registry,
        approvals=approvals,
        execution_ledger=ledger,
        promotion_store=promotion_store,
    )
    return factory, approvals, ledger, promotion


def standing(promotion):
    return StandingPolicyAuthorization(
        playbook_id="unexpected-shutdown",
        playbook_version="1.0.0",
        policy_id="approved-autonomous-playbook",
        promotion_approval_id=promotion.approval_id,
    )


def test_missing_exact_grant_fails_closed(tmp_path):
    factory, _, _, promotion = build(tmp_path, with_grant=False)
    with pytest.raises(AutonomousAuthorityError):
        factory.build(
            capability_name="service.ticket.update",
            arguments={"payload": {"id": 123, "queueID": 1}},
            client_id=None,
            standing_policy=standing(promotion),
        )


def test_approval_required_capability_needs_approved_playbook_policy(tmp_path):
    factory, _, _, promotion = build(tmp_path)
    with pytest.raises(AutonomousAuthorityError):
        factory.build(
            capability_name="service.ticket.update",
            arguments={"payload": {"id": 123, "queueID": 1}},
            client_id=None,
        )


def test_service_principal_gets_exact_short_lived_approval(tmp_path):
    factory, approvals, ledger, promotion = build(tmp_path)
    request = factory.build(
        capability_name="service.ticket.update",
        arguments={"payload": {"id": 123, "queueID": 1}},
        client_id=None,
        standing_policy=standing(promotion),
    )
    assert request.requester_kind == "service"
    assert request.principal_id == "jason-autonomy-worker"
    assert request.approval_present is True
    assert request.approval_id
    assert request.idempotency_key
    record = approvals.get(request.approval_id)
    assert record is not None
    assert record.requested_by == "jason-autonomy-worker"
    assert record.decided_by.startswith("policy:approved-autonomous-playbook")
    evidence = ledger.evidence(request.approval_id)
    assert evidence["state"] == "reserved"


def test_same_exact_intent_reuses_reservation_not_new_authority(tmp_path):
    factory, approvals, ledger, promotion = build(tmp_path)
    args = {"payload": {"id": 123, "queueID": 1}}
    first = factory.build(
        capability_name="service.ticket.update",
        arguments=args,
        client_id=None,
        standing_policy=standing(promotion),
    )
    second = factory.build(
        capability_name="service.ticket.update",
        arguments=args,
        client_id=None,
        standing_policy=standing(promotion),
    )
    assert first.approval_id == second.approval_id
    assert first.idempotency_key == second.idempotency_key


def test_nonapproval_capability_still_requires_service_grant(tmp_path):
    factory, _, _, promotion = build(tmp_path, approval_required=False)
    request = factory.build(
        capability_name="service.ticket.update",
        arguments={"payload": {"id": 123, "queueID": 1}},
        client_id=None,
    )
    assert request.approval_id is None
    assert request.approval_present is False
