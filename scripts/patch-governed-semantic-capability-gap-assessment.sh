#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START GOVERNED SEMANTIC CAPABILITY GAP ASSESSMENT =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: ADD STRUCTURED PROVIDER-NEUTRAL GAP ASSESSOR =========="
cat > implementation/orchestrator/semantic_capability_gap.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SemanticCapabilityGapAssessment:
    unsupported_facts: tuple[str, ...]
    inspected_context_views: tuple[str, ...]
    gap_type: str = "capability_registry_gap"
    governance_owner: str = "technology-steward"
    recommended_next_action: str = (
        "Review registered execution providers and their authoritative documentation for an existing "
        "read-only capability that can satisfy the unsupported facts. If support exists, expand the "
        "provider-neutral capability/evidence metadata through normal governance. If support does not "
        "exist, record the gap without inventing a provider mapping or one-off workflow."
    )

    def as_context(self) -> Mapping[str, Any]:
        return {
            "gap_type": self.gap_type,
            "unsupported_facts": self.unsupported_facts,
            "inspected_context_views": self.inspected_context_views,
            "governance_owner": self.governance_owner,
            "recommended_next_action": self.recommended_next_action,
        }


@dataclass(frozen=True, slots=True)
class GovernedSemanticCapabilityGapAssessor:
    """Translate a conclusive fulfillment failure into a governed expansion work item.

    The assessor does not select providers, call provider APIs, inspect credentials, or mutate the
    capability registry. It records what the planner proved unavailable and identifies the normal
    Technology Steward review path for discovering whether an existing registered provider already
    exposes the needed read capability.
    """

    inspected_context_views: tuple[str, ...] = (
        "capability_registry",
        "evidence_catalog",
        "derivation_registry",
    )

    def assess(self, *, feasibility_result: Any) -> SemanticCapabilityGapAssessment | None:
        if not bool(getattr(feasibility_result, "conclusive", False)):
            return None
        if bool(getattr(feasibility_result, "feasible", False)):
            return None
        unsupported = tuple(
            str(item).strip()
            for item in getattr(feasibility_result, "unsupported_facts", ())
            if str(item).strip()
        )
        if not unsupported:
            return None
        return SemanticCapabilityGapAssessment(
            unsupported_facts=unsupported,
            inspected_context_views=self.inspected_context_views,
        )
PY

echo "WROTE: implementation/orchestrator/semantic_capability_gap.py"

echo "========== SECTION 3: EXTEND PLANNING OUTCOME WITH GOVERNED GAP DETAILS =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/semantic_intent_planning_loop.py")
text = path.read_text()

old = '''class IntentPlanSufficiencyValidator(Protocol):\n    def validate(\n        self,\n        *,\n        intent: Mapping[str, Any],\n        plan: FulfillmentPlanCandidate,\n        context: Mapping[str, Any],\n    ) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
new = '''class IntentPlanSufficiencyValidator(Protocol):\n    def validate(\n        self,\n        *,\n        intent: Mapping[str, Any],\n        plan: FulfillmentPlanCandidate,\n        context: Mapping[str, Any],\n    ) -> Any: ...\n\n\nclass IntentCapabilityGapAssessor(Protocol):\n    def assess(self, *, feasibility_result: Any) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
if old not in text:
    raise SystemExit("planning-loop protocol insertion marker not found")
text = text.replace(old, new, 1)

old = '''    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n    plan_validator: IntentPlanSufficiencyValidator | None = None\n'''
new = '''    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n    plan_validator: IntentPlanSufficiencyValidator | None = None\n    feasibility_gate: Any | None = None\n    capability_gap_assessor: IntentCapabilityGapAssessor | None = None\n'''
if old not in text:
    if '    feasibility_gate:' not in text:
        raise SystemExit("planning-loop field insertion marker not found")
else:
    text = text.replace(old, new, 1)

# If feasibility_gate already existed from prior work, add only the gap assessor after it.
if '    capability_gap_assessor: IntentCapabilityGapAssessor | None = None\n' not in text:
    marker = '    feasibility_gate: Any | None = None\n'
    if marker not in text:
        raise SystemExit("existing feasibility_gate field not found")
    text = text.replace(marker, marker + '    capability_gap_assessor: IntentCapabilityGapAssessor | None = None\n', 1)

# Add optional gap_details to outcome with a default to preserve all existing call sites.
old = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n'''
new = '''class IntentPlanningOutcome:\n    status: str\n    plan: FulfillmentPlanCandidate | None\n    gap_summary: str | None\n    trace: tuple[PlanningTraceEntry, ...]\n    iterations_used: int\n    context_requests_used: int\n    gap_details: Mapping[str, Any] | None = None\n'''
if old not in text:
    raise SystemExit("IntentPlanningOutcome marker not found")
text = text.replace(old, new, 1)

# Locate the current fulfillment-infeasible return and attach structured gap details.
needle = 'status="fulfillment_infeasible"'
if needle not in text:
    raise SystemExit("fulfillment infeasible trace marker not found")

# Insert gap assessment immediately before the infeasible trace append.
marker = '                        trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'
insert = '''                        gap_details = None\n                        if self.capability_gap_assessor is not None:\n                            assessment = self.capability_gap_assessor.assess(\n                                feasibility_result=feasibility,\n                            )\n                            if assessment is not None:\n                                as_context = getattr(assessment, "as_context", None)\n                                if callable(as_context):\n                                    gap_details = dict(as_context())\n                                    _reject_forbidden_keys(gap_details)\n                        trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n'''
if marker not in text:
    raise SystemExit("fulfillment infeasible return marker not found")
text = text.replace(marker, insert, 1)

# Add gap_details to the following infeasible outcome only.
search_start = text.index('gap_details = None', text.index(needle) - 2500 if text.index(needle) > 2500 else 0)
return_marker = '                            context_requests_used=context_requests,\n                        )\n'
pos = text.find(return_marker, search_start)
if pos == -1:
    raise SystemExit("fulfillment infeasible outcome marker not found")
replacement = '                            context_requests_used=context_requests,\n                            gap_details=gap_details,\n                        )\n'
text = text[:pos] + text[pos:].replace(return_marker, replacement, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat > implementation/orchestrator/tests/test_semantic_capability_gap.py <<'PY'
from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor
from orchestrator.semantic_fulfillment_feasibility import FulfillmentFeasibilityResult


def test_conclusive_infeasible_result_becomes_governed_capability_gap():
    assessment = GovernedSemanticCapabilityGapAssessor().assess(
        feasibility_result=FulfillmentFeasibilityResult(
            conclusive=True,
            feasible=False,
            unsupported_facts=("special governed fact",),
            summary="unsupported",
        )
    )
    assert assessment is not None
    context = assessment.as_context()
    assert context["gap_type"] == "capability_registry_gap"
    assert context["unsupported_facts"] == ("special governed fact",)
    assert context["governance_owner"] == "technology-steward"
    assert "authoritative documentation" in context["recommended_next_action"]


def test_feasible_or_inconclusive_result_does_not_create_gap():
    assessor = GovernedSemanticCapabilityGapAssessor()
    assert assessor.assess(
        feasibility_result=FulfillmentFeasibilityResult(conclusive=False, feasible=False)
    ) is None
    assert assessor.assess(
        feasibility_result=FulfillmentFeasibilityResult(conclusive=True, feasible=True)
    ) is None
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_capability_gap.py"

"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/tests/test_semantic_intent_planning_loop.py")
text = path.read_text()
append = r'''


def test_fulfillment_infeasible_outcome_exposes_governed_capability_gap_details():
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

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=Validator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
        capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ("special governed fact",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.gap_details is not None
    assert outcome.gap_details["gap_type"] == "capability_registry_gap"
    assert outcome.gap_details["unsupported_facts"] == ("special governed fact",)
'''
if 'test_fulfillment_infeasible_outcome_exposes_governed_capability_gap_details' not in text:
    path.write_text(text + append)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: regression already present in {path}")
PY

echo "========== SECTION 5: ENABLE GAP ASSESSMENT IN LIVE OBSERVE-ONLY PROBE =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()

import_marker = 'from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate\n'
if import_marker not in text:
    raise SystemExit("live probe feasibility import marker not found")
if 'from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor\n' not in text:
    text = text.replace(
        import_marker,
        import_marker + 'from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor\n',
        1,
    )

field_marker = '    feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),\n'
if field_marker not in text:
    raise SystemExit("live probe feasibility field marker not found")
if '    capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),\n' not in text:
    text = text.replace(
        field_marker,
        field_marker + '    capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),\n',
        1,
    )

print_marker = 'if outcome.gap_summary:\n    print(f"KNOWLEDGE_GAP={outcome.gap_summary}")\n'
if print_marker not in text:
    raise SystemExit("live probe gap output marker not found")
if 'CAPABILITY_GAP_TYPE=' not in text:
    text = text.replace(
        print_marker,
        print_marker + '''if outcome.gap_details:\n    print(f"CAPABILITY_GAP_TYPE={outcome.gap_details.get('gap_type', '-')}")\n    print(f"CAPABILITY_GAP_FACTS={','.join(outcome.gap_details.get('unsupported_facts', ())) or '-'}")\n    print(f"CAPABILITY_GAP_OWNER={outcome.gap_details.get('governance_owner', '-')}")\n    print(f"CAPABILITY_GAP_NEXT_ACTION={outcome.gap_details.get('recommended_next_action', '-')}")\n''',
        1,
    )

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 6: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 7: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_capability_gap.py \
  implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Conclusive semantic fulfillment failures now produce a structured provider-neutral capability-registry gap assessment."
echo "The assessment routes future discovery to the Technology Steward and authoritative registered-provider documentation without selecting a provider or creating a one-off workflow."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED SEMANTIC CAPABILITY GAP ASSESSMENT =========="
