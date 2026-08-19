#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START WIRE GOVERNED PROVIDER DISCOVERY INTO GAP PATH =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: EXTEND PLANNING OUTCOME WITH PROVIDER DISCOVERY =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/semantic_intent_planning_loop.py")
text = path.read_text()

outcome_old = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n    gap_details: Mapping[str, Any] | None = None\n'''
outcome_new = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n    gap_details: Mapping[str, Any] | None = None\n    provider_discovery: Mapping[str, Any] | None = None\n'''
if outcome_old not in text:
    raise SystemExit("IntentPlanningOutcome extension marker not found")
text = text.replace(outcome_old, outcome_new, 1)

protocol_marker = '''class IntentCapabilityGapAssessor(Protocol):\n    def assess(self, *, feasibility_result: Any) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
protocol_insert = '''class IntentCapabilityGapAssessor(Protocol):\n    def assess(self, *, feasibility_result: Any) -> Any: ...\n\n\nclass IntentProviderCapabilityDiscovery(Protocol):\n    def discover(self, *, gap: Any, providers: Sequence[Any]) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
if protocol_marker not in text:
    raise SystemExit("provider discovery protocol marker not found")
text = text.replace(protocol_marker, protocol_insert, 1)

field_marker = '    capability_gap_assessor: IntentCapabilityGapAssessor | None = None\n'
if field_marker not in text:
    raise SystemExit("capability gap assessor field marker not found")
text = text.replace(
    field_marker,
    field_marker
    + '    provider_discovery: IntentProviderCapabilityDiscovery | None = None\n'
    + '    provider_discovery_records: Sequence[Any] = ()\n',
    1,
)

infeasible_marker = '''                        gap_details = None\n                        if self.capability_gap_assessor is not None:\n                            assessment = self.capability_gap_assessor.assess(\n                                feasibility_result=feasibility,\n                            )\n                            if assessment is not None:\n                                as_context = getattr(assessment, "as_context", None)\n                                if callable(as_context):\n                                    gap_details = dict(as_context())\n                                    _reject_forbidden_keys(gap_details)\n                        trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'''
replacement = '''                        gap_details = None\n                        gap_assessment = None\n                        if self.capability_gap_assessor is not None:\n                            gap_assessment = self.capability_gap_assessor.assess(\n                                feasibility_result=feasibility,\n                            )\n                            if gap_assessment is not None:\n                                as_context = getattr(gap_assessment, "as_context", None)\n                                if callable(as_context):\n                                    gap_details = dict(as_context())\n                                    _reject_forbidden_keys(gap_details)\n\n                        provider_discovery = None\n                        if (\n                            gap_assessment is not None\n                            and self.provider_discovery is not None\n                            and self.provider_discovery_records\n                        ):\n                            discovery = self.provider_discovery.discover(\n                                gap=gap_assessment,\n                                providers=tuple(self.provider_discovery_records),\n                            )\n                            as_context = getattr(discovery, "as_context", None)\n                            if callable(as_context):\n                                provider_discovery = dict(as_context())\n                                _reject_forbidden_keys(provider_discovery)\n\n                        trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'''
if infeasible_marker not in text:
    raise SystemExit("fulfillment infeasible assessment marker not found")
text = text.replace(infeasible_marker, replacement, 1)

outcome_return_marker = '''                                    context_requests_used=context_requests,\n                                    gap_details=gap_details,\n                                )\n'''
if outcome_return_marker not in text:
    raise SystemExit("infeasible outcome return marker not found")
text = text.replace(
    outcome_return_marker,
    '''                                    context_requests_used=context_requests,\n                                    gap_details=gap_details,\n                                    provider_discovery=provider_discovery,\n                                )\n''',
    1,
)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD GENERALIZED REGRESSION COVERAGE =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/tests/test_semantic_intent_planning_loop.py")
text = path.read_text()
append = r'''


def test_fulfillment_infeasible_outcome_exposes_review_only_provider_discovery():
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
            class Result:
                sufficient = False
                issues = ("unsupported",)
            return Result()

    now = datetime.now(timezone.utc)
    provider = ExecutionProvider(
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
        limits=ProviderLimits(maximum_execution_seconds=30),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="test",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("test",),
            vendor_change_sources=("Example authoritative API documentation",),
        ),
        created_at=now,
        metadata={"connector_id": "example", "resource_authority": "managed_endpoint"},
    )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=Validator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
        capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),
        provider_discovery=GovernedProviderCapabilityDiscovery(),
        provider_discovery_records=(provider,),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ("special governed fact",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.provider_discovery is not None
    assert outcome.provider_discovery["review_only"] is True
    assert outcome.provider_discovery["unsupported_facts"] == ("special governed fact",)
    assert outcome.provider_discovery["candidates"][0]["provider_id"] == "example_provider"
    assert outcome.provider_discovery["candidates"][0]["vendor_change_sources"] == (
        "Example authoritative API documentation",
    )
'''
if 'test_fulfillment_infeasible_outcome_exposes_review_only_provider_discovery' not in text:
    path.write_text(text + append)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: regression already present in {path}")
PY

echo "========== SECTION 4: WIRE LIVE OBSERVE-ONLY PROBE =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()

import_marker = 'from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor\n'
if import_marker not in text:
    raise SystemExit("capability gap import marker not found")
if 'from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery\n' not in text:
    text = text.replace(
        import_marker,
        import_marker + 'from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery\n',
        1,
    )

provider_build_marker = 'registry = build_trusted_semantic_registry()\n'
provider_build = '''provider_records = (\n    datto_rmm_endpoint_provider(now),\n)\n\nregistry = build_trusted_semantic_registry()\n'''
if provider_build_marker not in text:
    raise SystemExit("live probe provider construction marker not found")
if 'provider_records = (' not in text:
    text = text.replace(provider_build_marker, provider_build, 1)

resource_import_marker = '    management_site_search,\n)\n'
resource_import_replacement = '    management_site_search,\n    datto_rmm_endpoint_provider,\n)\n'
if resource_import_marker not in text:
    raise SystemExit("resource capability import marker not found")
if '    datto_rmm_endpoint_provider,\n' not in text:
    text = text.replace(resource_import_marker, resource_import_replacement, 1)

planner_marker = '    capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),\n'
planner_replacement = '''    capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),\n    provider_discovery=GovernedProviderCapabilityDiscovery(),\n    provider_discovery_records=provider_records,\n'''
if planner_marker not in text:
    raise SystemExit("planner capability gap field marker not found")
if '    provider_discovery=GovernedProviderCapabilityDiscovery(),\n' not in text:
    text = text.replace(planner_marker, planner_replacement, 1)

print_marker = '''if outcome.gap_details:\n    print(f"CAPABILITY_GAP_TYPE={outcome.gap_details.get('gap_type', '-')}")\n    print(f"CAPABILITY_GAP_FACTS={','.join(outcome.gap_details.get('unsupported_facts', ())) or '-'}")\n    print(f"CAPABILITY_GAP_OWNER={outcome.gap_details.get('governance_owner', '-')}")\n    print(f"CAPABILITY_GAP_NEXT_ACTION={outcome.gap_details.get('recommended_next_action', '-')}")\n'''
print_replacement = print_marker + '''if outcome.provider_discovery:\n    print(f"PROVIDER_DISCOVERY_REVIEW_ONLY={outcome.provider_discovery.get('review_only', False)}")\n    print(f"PROVIDER_DISCOVERY_OWNER={outcome.provider_discovery.get('governance_owner', '-')}")\n    candidates = outcome.provider_discovery.get('candidates', ())\n    print(f"PROVIDER_DISCOVERY_CANDIDATE_COUNT={len(candidates)}")\n    for index, candidate in enumerate(candidates, 1):\n        print(f"PROVIDER_DISCOVERY[{index}] id={candidate.get('provider_id', '-')} name={candidate.get('display_name', '-')}")\n        print(f"PROVIDER_DISCOVERY[{index}] capabilities={','.join(candidate.get('registered_capabilities', ())) or '-'}")\n        print(f"PROVIDER_DISCOVERY[{index}] sources={' | '.join(candidate.get('vendor_change_sources', ())) or '-'}")\n        print(f"PROVIDER_DISCOVERY[{index}] resource_authority={candidate.get('resource_authority', '-')}")\n'''
if print_marker not in text:
    raise SystemExit("live probe capability gap output marker not found")
if 'PROVIDER_DISCOVERY_REVIEW_ONLY=' not in text:
    text = text.replace(print_marker, print_replacement, 1)

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
echo "Conclusive capability gaps now expose review-only registered-provider discovery candidates and authoritative vendor documentation sources."
echo "Discovery remains non-executing and does not infer semantic mappings, inspect credentials, or mutate registries."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END WIRE GOVERNED PROVIDER DISCOVERY INTO GAP PATH =========="
