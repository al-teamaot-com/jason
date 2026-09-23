#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START WIRE GOVERNED PROVIDER DISCOVERY INTO GAP PATH REPAIR V2 =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: EXTEND CURRENT PLANNING OUTCOME CONTRACT =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/semantic_intent_planning_loop.py")
text = path.read_text()

old = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n    gap_details: Mapping[str, Any] | None = None\n'''
new = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n    gap_details: Mapping[str, Any] | None = None\n    provider_discovery_details: Mapping[str, Any] | None = None\n'''
if '    provider_discovery_details: Mapping[str, Any] | None = None\n' not in text:
    if old not in text:
        raise SystemExit("current IntentPlanningOutcome marker not found")
    text = text.replace(old, new, 1)

old = '''class IntentCapabilityGapAssessor(Protocol):\n    def assess(self, *, feasibility_result: Any) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
new = '''class IntentCapabilityGapAssessor(Protocol):\n    def assess(self, *, feasibility_result: Any) -> Any: ...\n\n\nclass IntentProviderCapabilityDiscovery(Protocol):\n    def discover(self, *, gap: Any, providers: Sequence[Any]) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
if 'class IntentProviderCapabilityDiscovery(Protocol):' not in text:
    if old not in text:
        raise SystemExit("current capability gap protocol marker not found")
    text = text.replace(old, new, 1)

field_marker = '    capability_gap_assessor: IntentCapabilityGapAssessor | None = None\n'
field_add = (
    field_marker
    + '    provider_capability_discovery: IntentProviderCapabilityDiscovery | None = None\n'
    + '    registered_providers: tuple[Any, ...] = ()\n'
)
if '    provider_capability_discovery: IntentProviderCapabilityDiscovery | None = None\n' not in text:
    if field_marker not in text:
        raise SystemExit("current capability gap assessor field marker not found")
    text = text.replace(field_marker, field_add, 1)

old = '''                                gap_details = None\n                                if self.capability_gap_assessor is not None:\n                                    assessment = self.capability_gap_assessor.assess(\n                                        feasibility_result=feasibility,\n                                    )\n                                    if assessment is not None:\n                                        as_context = getattr(assessment, "as_context", None)\n                                        if callable(as_context):\n                                            gap_details = dict(as_context())\n                                            _reject_forbidden_keys(gap_details)\n                                trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'''
new = '''                                gap_details = None\n                                provider_discovery_details = None\n                                assessment = None\n                                if self.capability_gap_assessor is not None:\n                                    assessment = self.capability_gap_assessor.assess(\n                                        feasibility_result=feasibility,\n                                    )\n                                    if assessment is not None:\n                                        as_context = getattr(assessment, "as_context", None)\n                                        if callable(as_context):\n                                            gap_details = dict(as_context())\n                                            _reject_forbidden_keys(gap_details)\n                                if (\n                                    assessment is not None\n                                    and self.provider_capability_discovery is not None\n                                ):\n                                    discovery = self.provider_capability_discovery.discover(\n                                        gap=assessment,\n                                        providers=tuple(self.registered_providers),\n                                    )\n                                    as_context = getattr(discovery, "as_context", None)\n                                    if callable(as_context):\n                                        provider_discovery_details = dict(as_context())\n                                trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'''
if 'provider_discovery_details = None' not in text:
    if old not in text:
        raise SystemExit("current fulfillment infeasible assessment block not found")
    text = text.replace(old, new, 1)

old = '''                                    context_requests_used=context_requests,\n                                    gap_details=gap_details,\n                                )\n'''
new = '''                                    context_requests_used=context_requests,\n                                    gap_details=gap_details,\n                                    provider_discovery_details=provider_discovery_details,\n                                )\n'''
if '                                    provider_discovery_details=provider_discovery_details,\n' not in text:
    if old not in text:
        raise SystemExit("current fulfillment infeasible outcome marker not found")
    text = text.replace(old, new, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD GENERALIZED INTEGRATION REGRESSION =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/tests/test_semantic_intent_planning_loop.py")
text = path.read_text()
append = r'''


def test_fulfillment_infeasible_outcome_exposes_review_only_provider_discovery():
    from dataclasses import dataclass
    from datetime import datetime, timezone

    from kernel.execution_providers import (
        ExecutionProvider,
        ProviderApproval,
        ProviderFeatures,
        ProviderHealth,
        ProviderLifecycle,
        ProviderLimits,
        ProviderStewardship,
        ProviderType,
    )
    from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery
    from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor
    from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(FulfillmentPlanStepCandidate(
                        capability_name="endpoint.device.search",
                        purpose="attempt governed read",
                    ),),
                    rationale_summary="candidate",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "view_name": request.view,
                    "items": ({"capability_name": "endpoint.device.search", "fact_hints": "hostname"},),
                    "capability_names": ("endpoint.device.search",),
                }
            return {"view_name": request.view, "items": ()}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(view="capability_registry"),
                PlanningContextRequest(view="evidence_catalog"),
                PlanningContextRequest(view="derivation_registry"),
            )

    class Validator:
        def validate(self, *, intent, plan, context):
            @dataclass(frozen=True)
            class Result:
                sufficient: bool = False
                issues: tuple[str, ...] = ("unsupported",)
            return Result()

    now = datetime.now(timezone.utc)
    registered_provider = ExecutionProvider(
        provider_id="example_provider",
        display_name="Example Provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"endpoint.device.search"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="test",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("retire",),
            vendor_change_sources=("Example Provider API documentation",),
        ),
        created_at=now,
        metadata={"resource_authority": "endpoint", "connector_id": "example"},
    )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=Validator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
        capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),
        provider_capability_discovery=GovernedProviderCapabilityDiscovery(),
        registered_providers=(registered_provider,),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ("special governed fact",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.provider_discovery_details is not None
    assert outcome.provider_discovery_details["review_only"] is True
    candidates = outcome.provider_discovery_details["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["provider_id"] == "example_provider"
    assert candidates[0]["vendor_change_sources"] == ("Example Provider API documentation",)
'''
if 'test_fulfillment_infeasible_outcome_exposes_review_only_provider_discovery' not in text:
    path.write_text(text + append)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: provider discovery integration regression already present in {path}")
PY

echo "========== SECTION 4: ENABLE REVIEW-ONLY DISCOVERY IN LIVE PROBE =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()

# Import registered provider constructor beside resource capability constructors.
old = '''    endpoint_software_search,\n    management_alert_search,\n    management_site_search,\n)\n'''
new = '''    endpoint_software_search,\n    management_alert_search,\n    management_site_search,\n    datto_rmm_endpoint_provider,\n)\n'''
if '    datto_rmm_endpoint_provider,\n' not in text:
    if old not in text:
        raise SystemExit("live probe resource capability import marker not found")
    text = text.replace(old, new, 1)

import_marker = 'from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor\n'
if 'from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery\n' not in text:
    if import_marker not in text:
        raise SystemExit("live probe capability gap import marker not found")
    text = text.replace(
        import_marker,
        import_marker + 'from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery\n',
        1,
    )

field_marker = '    capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),\n'
field_add = (
    field_marker
    + '    provider_capability_discovery=GovernedProviderCapabilityDiscovery(),\n'
    + '    registered_providers=(datto_rmm_endpoint_provider(now),),\n'
)
if '    provider_capability_discovery=GovernedProviderCapabilityDiscovery(),\n' not in text:
    if field_marker not in text:
        raise SystemExit("live probe capability gap assessor field marker not found")
    text = text.replace(field_marker, field_add, 1)

print_marker = '''    print(f"CAPABILITY_GAP_NEXT_ACTION={outcome.gap_details.get('recommended_next_action', '-')}")\n'''
print_add = print_marker + '''if outcome.provider_discovery_details:\n    print(f"PROVIDER_DISCOVERY_REVIEW_ONLY={outcome.provider_discovery_details.get('review_only', False)}")\n    candidates = outcome.provider_discovery_details.get("candidates", ())\n    print(f"PROVIDER_DISCOVERY_CANDIDATE_COUNT={len(candidates)}")\n    for index, candidate in enumerate(candidates, 1):\n        print(f"PROVIDER_DISCOVERY[{index}]_ID={candidate.get('provider_id', '-')}")\n        print(f"PROVIDER_DISCOVERY[{index}]_DOCS={' | '.join(candidate.get('vendor_change_sources', ())) or '-'}")\n        print(f"PROVIDER_DISCOVERY[{index}]_AUTHORITY={candidate.get('resource_authority', '-') or '-'}")\n'''
if 'PROVIDER_DISCOVERY_REVIEW_ONLY=' not in text:
    if print_marker not in text:
        raise SystemExit("live probe capability gap output marker not found")
    text = text.replace(print_marker, print_add, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 5: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 6: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_provider_capability_discovery.py \
  implementation/orchestrator/tests/test_semantic_capability_gap.py \
  implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py

echo "========== SECTION 7: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Review-only registered-provider capability discovery is now wired into conclusive semantic capability gaps."
echo "The planning outcome may expose governed provider documentation candidates after infeasibility is proven."
echo "Provider discovery remains outside reasoner authority and does not call providers, inspect credentials, infer mappings, select execution providers, or mutate registries."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END WIRE GOVERNED PROVIDER DISCOVERY INTO GAP PATH REPAIR V2 =========="
