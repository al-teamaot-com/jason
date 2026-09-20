from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle, CapabilityRisk, IdempotencyBehavior
from orchestrator.provider_mutation_capability_catalog import (
    AUTOTASK_MUTATION_CAPABILITIES,
    SERVICE_TICKET_CREATE,
    SERVICE_TICKET_NOTE_CREATE,
    SERVICE_TICKET_NOTE_UPDATE,
    SERVICE_TICKET_UPDATE,
    autotask_mutation_capability_definitions,
)


NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def _definitions():
    return autotask_mutation_capability_definitions(now=NOW)


def test_autotask_mutation_catalog_contains_only_approved_pilot_operations() -> None:
    definitions = _definitions()

    assert {item.capability_name for item in definitions} == set(
        AUTOTASK_MUTATION_CAPABILITIES
    )
    assert {
        SERVICE_TICKET_CREATE,
        SERVICE_TICKET_UPDATE,
        SERVICE_TICKET_NOTE_CREATE,
        SERVICE_TICKET_NOTE_UPDATE,
    }.issubset(AUTOTASK_MUTATION_CAPABILITIES)
    assert all("delete" not in item.capability_name for item in definitions)
    assert any(name.startswith("service.product.") for name in AUTOTASK_MUTATION_CAPABILITIES)
    assert any(name.startswith("service.service.") for name in AUTOTASK_MUTATION_CAPABILITIES)
    assert any(name.startswith("service.purchase.order.") for name in AUTOTASK_MUTATION_CAPABILITIES)


def test_mutation_definitions_are_dormant_high_risk_and_owner_approved() -> None:
    for definition in _definitions():
        assert definition.lifecycle_status is CapabilityLifecycle.BUILDING
        assert definition.risk_level is CapabilityRisk.HIGH
        assert definition.approval.required is True
        assert definition.approval.approver_classes == ("owner",)
        assert definition.maximum_attempts == 1
        assert definition.idempotency_key_required is True
        assert definition.tenant_isolation_required is True
        assert definition.client_isolation_required is True
        assert definition.metadata["read_only"] == "false"
        assert definition.metadata["activation_state"] == "source_only_not_registered"
        assert definition.metadata["provider_native_impersonation_required"] == "true"
        assert (
            definition.metadata["requester_provider_profile_is_maximum_authority"]
            == "true"
        )


def test_create_operations_are_non_idempotent_and_updates_are_conditional() -> None:
    definitions = {item.capability_name: item for item in _definitions()}

    for name, definition in definitions.items():
        if name.endswith(".create"):
            assert (
                definition.idempotency_behavior
                is IdempotencyBehavior.NON_IDEMPOTENT
            )
        elif name.endswith(".update"):
            assert (
                definition.idempotency_behavior
                is IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT
            )
        else:
            raise AssertionError(f"unexpected mutation operation: {name}")


def test_mutation_catalog_has_no_registration_or_activation_side_effect() -> None:
    # This module returns definitions only. Production composition must make a
    # separate deliberate choice to register and later activate them.
    definitions = _definitions()

    assert len(definitions) == len(AUTOTASK_MUTATION_CAPABILITIES)
    assert all(
        definition.lifecycle_status is not CapabilityLifecycle.ACTIVE
        for definition in definitions
    )
