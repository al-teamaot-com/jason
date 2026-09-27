from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)

from .reflection_runtime import (
    REFLECTION_CANDIDATE_READ,
    REFLECTION_CANDIDATE_SEARCH,
    REFLECTION_PROVIDER,
)


def build_reflection_manifest() -> IntegrationManifest:
    """Expose reflection review evidence, never correction/review mutations."""
    return IntegrationManifest(
        integration_id="reflection_memory",
        display_name="Jason Governed Reflection",
        manifest_version="1.0",
        provider_id=REFLECTION_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="improvement_candidate",
                description=(
                    "Human-reviewed continuous-improvement candidates produced from bounded "
                    "execution telemetry and authenticated technician corrections. Candidates "
                    "are evidence only and cannot change production behavior or authority."
                ),
                selectors=(
                    SelectorDefinition(name="state", description="Optional candidate lifecycle state."),
                    SelectorDefinition(name="limit", description="Bounded maximum candidates to return."),
                    SelectorDefinition(
                        name="candidate_key",
                        description="Durable reflection candidate identity.",
                        verified_identity_required=True,
                    ),
                ),
                operations=(
                    IntegrationOperation(
                        operation_id="reflection.candidate.search",
                        kind=OperationKind.SEARCH,
                        capability_name=REFLECTION_CANDIDATE_SEARCH,
                        description="Search governed reflection candidates for review.",
                        read_only=True,
                        selector_names=("state", "limit"),
                        collection_supported=True,
                    ),
                    IntegrationOperation(
                        operation_id="reflection.candidate.read",
                        kind=OperationKind.READ,
                        capability_name=REFLECTION_CANDIDATE_READ,
                        description="Read one reflection candidate and its regression evidence.",
                        read_only=True,
                        selector_names=("candidate_key",),
                        collection_supported=False,
                    ),
                ),
                observations=(
                    ResourceObservation("proposal", "Generic improvement proposal and rationale."),
                    ResourceObservation("review_state", "Observed/proposed/tested/approved/promoted/rejected lifecycle."),
                    ResourceObservation("regression_evidence", "Durable CI regression evidence attached before approval."),
                ),
            ),
        ),
        metadata={
            "authority": "evidence_only",
            "grants_authority": "false",
            "self_modifying": "false",
        },
    )
