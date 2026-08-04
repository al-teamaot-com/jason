from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityNotFoundError,
    CapabilityQuery,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    DuplicateCapabilityError,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def capability(
    *,
    capability_name: str = "governance.action.evaluate",
    version: str = "1.0",
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.ACTIVE,
    risk: CapabilityRisk = CapabilityRisk.HIGH,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version=version,
        display_name="Evaluate Governed Action",
        lifecycle_status=lifecycle,
        business_purpose=(
            "Determine whether a requested action may proceed."
        ),
        owner_service="Jason Governance Engine",
        architectural_capability_ids=frozenset({"JAC-006"}),
        risk_level=risk,
        data_classifications=frozenset(
            {"internal", "confidential"}
        ),
        permitted_execution_modes=frozenset(
            {"deterministic"}
        ),
        input_schema_reference=(
            "schema://governance.action.evaluate/input/1.0"
        ),
        output_schema_reference=(
            "schema://governance.action.evaluate/output/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "request facts",
                "applicable policy versions",
                "decision result",
            ),
        ),
        dependencies=frozenset(
            {"identity.authorization.resolve"}
        ),
        idempotency_behavior=(
            IdempotencyBehavior.IDEMPOTENT
        ),
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed and return a structured denial or error."
        ),
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="architecture-authority",
            business_justification=(
                "Central governed action evaluation is required."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by an approved equivalent capability.",
            ),
        ),
        created_at=NOW,
    )


def service() -> CapabilityRegistryService:
    return CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )


def test_registers_and_retrieves_capability() -> None:
    registry = service()
    record = capability()

    registry.register(record)

    assert registry.get(
        capability_name=record.capability_name,
        version=record.version,
    ) == record
    assert registry.list_all() == (record,)


def test_rejects_duplicate_name_and_version() -> None:
    registry = service()
    record = capability()

    registry.register(record)

    with pytest.raises(DuplicateCapabilityError):
        registry.register(record)


def test_missing_capability_raises_not_found() -> None:
    registry = service()

    with pytest.raises(CapabilityNotFoundError):
        registry.get(
            capability_name="missing.capability.read",
            version="1.0",
        )


def test_rejects_invalid_canonical_name() -> None:
    with pytest.raises(ValueError, match="Invalid capability name"):
        capability(
            capability_name="Governance.action.evaluate"
        )


def test_rejects_self_dependency() -> None:
    record = capability()

    with pytest.raises(ValueError, match="depend on itself"):
        replace(
            record,
            dependencies=frozenset(
                {record.capability_name}
            ),
        )


def test_current_version_resolves_highest_active_version() -> None:
    registry = service()

    registry.register(capability(version="1.0"))
    registry.register(capability(version="1.9"))
    registry.register(capability(version="1.10"))

    current = registry.get_current(
        capability_name="governance.action.evaluate"
    )

    assert current.version == "1.10"


def test_pilot_version_requires_explicit_permission() -> None:
    registry = service()

    registry.register(
        capability(
            version="1.0",
            lifecycle=CapabilityLifecycle.ACTIVE,
        )
    )
    registry.register(
        capability(
            version="2.0",
            lifecycle=CapabilityLifecycle.PILOT,
        )
    )

    normal = registry.get_current(
        capability_name="governance.action.evaluate"
    )
    pilot = registry.get_current(
        capability_name="governance.action.evaluate",
        allow_pilot=True,
    )

    assert normal.version == "1.0"
    assert pilot.version == "2.0"


def test_find_filters_capabilities_deterministically() -> None:
    registry = service()

    matching = capability(
        capability_name="governance.action.evaluate",
        version="1.0",
        lifecycle=CapabilityLifecycle.ACTIVE,
        risk=CapabilityRisk.HIGH,
    )
    other = capability(
        capability_name="evidence.record.query",
        version="1.0",
        lifecycle=CapabilityLifecycle.PILOT,
        risk=CapabilityRisk.MEDIUM,
    )

    registry.register(other)
    registry.register(matching)

    result = registry.find(
        CapabilityQuery(
            lifecycle_status=CapabilityLifecycle.ACTIVE,
            architectural_capability_id="JAC-006",
            execution_mode="deterministic",
            risk_level=CapabilityRisk.HIGH,
        )
    )

    assert result == (matching,)


@pytest.mark.parametrize(
    ("field_name", "replacement", "message"),
    [
        (
            "business_purpose",
            "",
            "business purpose",
        ),
        (
            "owner_service",
            "",
            "owner service",
        ),
        (
            "architectural_capability_ids",
            frozenset(),
            "architectural capability ID",
        ),
        (
            "data_classifications",
            frozenset(),
            "data classification",
        ),
        (
            "permitted_execution_modes",
            frozenset(),
            "execution mode",
        ),
        (
            "input_schema_reference",
            "",
            "input schema reference",
        ),
        (
            "output_schema_reference",
            "",
            "output schema reference",
        ),
        (
            "invoking_roles",
            frozenset(),
            "invoking role",
        ),
        (
            "failure_behavior",
            "",
            "failure behavior",
        ),
    ],
)
def test_active_capability_requires_governance_metadata(
    field_name: str,
    replacement: object,
    message: str,
) -> None:
    registry = service()
    record = capability()

    incomplete = replace(
        record,
        **{field_name: replacement},
    )

    with pytest.raises(ValueError, match=message):
        registry.register(incomplete)


def test_non_active_capability_may_be_registered_incomplete() -> None:
    registry = service()
    record = capability(
        lifecycle=CapabilityLifecycle.PROPOSED,
    )

    incomplete = replace(
        record,
        business_purpose="",
        owner_service="",
        architectural_capability_ids=frozenset(),
        data_classifications=frozenset(),
        permitted_execution_modes=frozenset(),
        input_schema_reference="",
        output_schema_reference="",
        invoking_roles=frozenset(),
        failure_behavior="",
    )

    registry.register(incomplete)

    assert registry.list_all() == (incomplete,)


def test_lifecycle_update_is_explicit_and_persisted() -> None:
    registry = service()
    record = capability(
        lifecycle=CapabilityLifecycle.BUILDING,
    )

    registry.register(record)

    updated = registry.set_lifecycle(
        capability_name=record.capability_name,
        version=record.version,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    assert updated.lifecycle_status is CapabilityLifecycle.ACTIVE
    assert registry.get(
        capability_name=record.capability_name,
        version=record.version,
    ) == updated


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1",
        "v1.0",
        "1.a",
        "1.0-beta",
    ],
)
def test_rejects_invalid_capability_version(
    version: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Invalid capability version",
    ):
        capability(version=version)


@pytest.mark.parametrize(
    "architectural_id",
    [
        "CAP-006",
        "JAC-6",
        "JAC-0006",
        "jac-006",
        "JAC-A06",
    ],
)
def test_rejects_invalid_architectural_capability_id(
    architectural_id: str,
) -> None:
    record = capability()

    with pytest.raises(
        ValueError,
        match="Invalid architectural capability ID",
    ):
        replace(
            record,
            architectural_capability_ids=frozenset(
                {architectural_id}
            ),
        )
