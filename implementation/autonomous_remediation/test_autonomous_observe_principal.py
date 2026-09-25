from __future__ import annotations

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

from .autonomous_principal import (
    AutonomousAuthorityError,
    AutonomousPrincipal,
    AutonomousRequestFactory,
)
from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore


CAPABILITY = "service.ticket.search"


def _capability():
    return CapabilityDefinition(
        capability_name=CAPABILITY,
        version="1.0",
        display_name="Ticket Search",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose="shadow queue read",
        owner_service="test",
        architectural_capability_ids=frozenset({"JAC-005"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://test/in",
        output_schema_reference="schema://test/out",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider evidence",),
            verification_requirements=("bounded result",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
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


def _factory(tmp_path, *, permission=PermissionMode.OBSERVE, with_grant=True):
    identities = InMemoryIdentityRepository()
    grants = InMemoryAuthorityGrantRepository()
    approvals = InMemoryApprovalRepository()
    identities.put(
        IdentityRecord("jason-autonomy-worker", "service", "aot")
    )
    if with_grant:
        grants.put(
            AuthorityGrant(
                grant_id="grant-shadow-read",
                subject_id="jason-autonomy-worker",
                capability=CAPABILITY,
                organization_id="aot",
                client_id=None,
                permission=permission,
                approval_required=False,
            )
        )
    authority = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
    )
    registry = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    registry.register(_capability())
    ledger = SQLiteGovernedExecutionLedger(
        str(tmp_path / "governed.sqlite3")
    )
    ledger.initialize()
    promotions = SQLitePlaybookAutonomyApprovalStore(
        tmp_path / "promotions.sqlite3"
    )
    return AutonomousRequestFactory(
        principal=AutonomousPrincipal(),
        authority=authority,
        capabilities=registry,
        approvals=approvals,
        execution_ledger=ledger,
        promotion_store=promotions,
    )


def test_observe_request_uses_nonhuman_workload_identity(tmp_path):
    request = _factory(tmp_path).build_observe(
        capability_name=CAPABILITY,
        arguments={"status": "New"},
        client_id=None,
    )
    assert request.principal_id == "jason-autonomy-worker"
    assert request.requester_kind == "service"
    assert request.permission_mode == "observe"
    assert request.approval_present is False
    assert request.policy_ids == ("autonomous-shadow-read-v1",)


def test_higher_execute_grant_cannot_change_shadow_request_mode(tmp_path):
    request = _factory(
        tmp_path,
        permission=PermissionMode.EXECUTE,
    ).build_observe(
        capability_name=CAPABILITY,
        arguments={"status": "New"},
        client_id=None,
    )
    assert request.permission_mode == "observe"
    assert request.requester_kind == "service"
    assert request.approval_present is False


def test_missing_grant_denies_shadow_read(tmp_path):
    factory = _factory(tmp_path, with_grant=False)
    with pytest.raises(AutonomousAuthorityError):
        factory.build_observe(
            capability_name=CAPABILITY,
            arguments={"status": "New"},
            client_id=None,
        )
