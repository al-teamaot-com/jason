from __future__ import annotations

import pytest

from orchestrator.conversation_kernel import InformationNeed, InformationTarget
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.conversation_resource_observation import observe_verified_resource
from orchestrator.information_fulfillment import FulfillmentCapability, FulfillmentStep
from orchestrator.information_need_intent import PlannedInformationNeed


def planned(*, kind="endpoint", reference="NODE-77", source="literal"):
    target = InformationTarget(
        kind=kind,
        source=source,
        reference=reference,
        entity_ref="existing-entity" if source == "verified_entity" else None,
    )
    need = InformationNeed(
        target=target,
        need="arbitrary governed information",
        authority="observe",
    )
    capability = FulfillmentCapability(
        capability_name=f"{kind}.resource.search",
        resource_types=(kind,),
        operation="search",
        selector_keys=("name",),
        role="primary",
        permission_mode="observe",
        risk="low",
        description="provider-neutral resource search",
    )
    return PlannedInformationNeed(
        need=need,
        step=FulfillmentStep(
            capability_name=capability.capability_name,
            target_reference=reference,
            target_source=source,
            information_need=need.need,
            authority="observe",
        ),
        capability=capability,
    )


def result(*, capability="endpoint.resource.search", data=None, status=OrchestrationStatus.SUCCEEDED):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name=capability,
        status=status,
        stage=(
            ExecutionStage.COMPLETED
            if status is OrchestrationStatus.SUCCEEDED
            else ExecutionStage.FAILED
        ),
        reason_codes=("test",),
        resolution=None,
        output={
            "provider": "provider-one",
            "data": data or {},
        },
        attempts=1,
        provider_id="provider-one",
    )


def resolved_data(resource_id="durable-123"):
    return {
        "resource_matches": [
            {
                "resource_id": resource_id,
                "display": "provider-returned-value",
            }
        ],
        "resolved_resource_id": resource_id,
        "provider_data": {"arbitrary": "evidence"},
    }


def test_literal_target_becomes_verified_entity_only_after_unique_durable_resolution():
    observation = observe_verified_resource(
        planned=planned(),
        result=result(data=resolved_data()),
    )

    assert observation is not None
    assert observation.entity.kind == "endpoint"
    assert observation.entity.canonical_id == "durable-123"
    assert observation.entity.display_name == "NODE-77"
    assert observation.resolution.mention == "NODE-77"
    assert observation.resolution.entity_ref == observation.entity.ref
    assert observation.active_kind == "endpoint"
    assert observation.entity.provenance == "governed resource resolution:exec-1"


def test_same_structural_contract_works_for_unrelated_future_resource_type():
    observation = observe_verified_resource(
        planned=planned(kind="printer", reference="PRINT-12"),
        result=result(
            capability="printer.resource.search",
            data=resolved_data("printer-durable-9"),
        ),
    )

    assert observation is not None
    assert observation.entity.kind == "printer"
    assert observation.entity.canonical_id == "printer-durable-9"
    assert observation.entity.display_name == "PRINT-12"


def test_selector_is_never_promoted_to_identity_when_provider_does_not_resolve_it():
    observation = observe_verified_resource(
        planned=planned(),
        result=result(
            data={
                "resource_matches": [
                    {"resource_id": "candidate-1"},
                    {"resource_id": "candidate-2"},
                ]
            }
        ),
    )

    assert observation is None


def test_inconsistent_resolution_fails_closed():
    with pytest.raises(RuntimeError, match="inconsistent"):
        observe_verified_resource(
            planned=planned(),
            result=result(
                data={
                    "resource_matches": [{"resource_id": "durable-A"}],
                    "resolved_resource_id": "durable-B",
                }
            ),
        )


def test_resolved_id_without_exactly_one_corroborating_match_fails_closed():
    with pytest.raises(RuntimeError, match="exactly one"):
        observe_verified_resource(
            planned=planned(),
            result=result(
                data={
                    "resource_matches": [
                        {"resource_id": "durable-1"},
                        {"resource_id": "durable-2"},
                    ],
                    "resolved_resource_id": "durable-1",
                }
            ),
        )


def test_existing_verified_entity_is_not_re_observed_from_provider_result():
    observation = observe_verified_resource(
        planned=planned(
            source="verified_entity",
            reference="durable-existing",
        ),
        result=result(data=resolved_data("durable-existing")),
    )

    assert observation is None


def test_failed_read_never_creates_verified_conversation_identity():
    observation = observe_verified_resource(
        planned=planned(),
        result=result(
            data=resolved_data(),
            status=OrchestrationStatus.FAILED,
        ),
    )

    assert observation is None
