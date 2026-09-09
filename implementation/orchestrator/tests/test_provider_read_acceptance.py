from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.provider_read_acceptance import (
    ProviderReadAcceptanceRecord,
    build_provider_read_activation_plan,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
)


NOW = datetime(2026, 9, 9, 21, 50, tzinfo=timezone.utc)


def record(**overrides: object) -> ProviderReadAcceptanceRecord:
    values: dict[str, object] = {
        "provider_id": IT_GLUE_PROVIDER,
        "observed_at": NOW,
        "evidence_reference": "evidence://provider-read/it-glue/20260909T215000Z",
        "verified_capabilities": frozenset({DOCUMENTATION_ORGANIZATION_SEARCH}),
        "status": "pass",
        "provider_backed": True,
        "read_only": True,
        "credential_boundary_proven": True,
        "protected_values_exposed": False,
        "raw_provider_payload_persisted": False,
        "hosted_model_used": False,
    }
    values.update(overrides)
    return ProviderReadAcceptanceRecord(**values)  # type: ignore[arg-type]


def test_builds_nonmutating_activation_plan_from_sanitized_live_evidence() -> None:
    plan = build_provider_read_activation_plan(record())

    assert plan.provider_id == IT_GLUE_PROVIDER
    assert plan.verified_capabilities == (DOCUMENTATION_ORGANIZATION_SEARCH,)
    assert plan.target_provider_lifecycle == "available"
    assert plan.target_provider_health == "healthy"
    assert plan.target_provider_approval == "approved"
    assert plan.target_capability_lifecycle == "active"
    assert plan.target_activation_state == "provider_backed_accepted"
    assert plan.hosted_model_required is False


def test_accepts_autotask_capability_without_provider_specific_mcp_tool() -> None:
    plan = build_provider_read_activation_plan(
        record(
            provider_id=AUTOTASK_PROVIDER,
            evidence_reference="evidence://provider-read/autotask/20260909T215000Z",
            verified_capabilities=frozenset({SERVICE_TICKET_SEARCH}),
            status="approved",
        )
    )

    assert plan.provider_id == AUTOTASK_PROVIDER
    assert plan.verified_capabilities == (SERVICE_TICKET_SEARCH,)
    assert plan.target_provider_approval == "approved"
    assert plan.hosted_model_required is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("provider_backed", False, "provider-backed"),
        ("read_only", False, "read-only"),
        ("credential_boundary_proven", False, "credential boundary"),
        ("protected_values_exposed", True, "Protected values"),
        ("raw_provider_payload_persisted", True, "Raw provider payload"),
        ("hosted_model_used", True, "hosted model"),
    ),
)
def test_rejects_acceptance_that_breaks_safety_or_cost_boundary(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(PermissionError, match=message):
        build_provider_read_activation_plan(record(**{field: value}))


def test_rejects_unverified_or_wrong_provider_capabilities() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_provider_read_activation_plan(record(verified_capabilities=frozenset()))

    with pytest.raises(ValueError, match="unsupported canonical capabilities"):
        build_provider_read_activation_plan(
            record(verified_capabilities=frozenset({SERVICE_TICKET_SEARCH}))
        )


def test_rejects_non_durable_or_naive_evidence_metadata() -> None:
    with pytest.raises(ValueError, match="durable evidence"):
        build_provider_read_activation_plan(record(evidence_reference=" "))

    with pytest.raises(ValueError, match="timezone-aware"):
        build_provider_read_activation_plan(
            record(observed_at=datetime(2026, 9, 9, 21, 50))
        )
