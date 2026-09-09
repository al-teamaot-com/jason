#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

echo "========== START GOVERNED SEMANTIC FULFILLMENT FEASIBILITY GATE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ADD PROVIDER-NEUTRAL FEASIBILITY GATE =========="
cat > implementation/orchestrator/semantic_fulfillment_feasibility.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _normalize(value: str) -> str:
    return " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )


def _requested_facts(intent: Mapping[str, Any]) -> tuple[str, ...]:
    raw = intent.get("requested_facts", ())
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, (list, tuple, set, frozenset)):
        values = tuple(str(item) for item in raw)
    else:
        values = ()
    return tuple(item.strip() for item in values if item.strip())


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _iter_strings(child)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            yield from _iter_strings(child)


@dataclass(frozen=True, slots=True)
class FulfillmentFeasibilityResult:
    conclusive: bool
    feasible: bool
    unsupported_facts: tuple[str, ...] = ()
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class GovernedSemanticFulfillmentFeasibilityGate:
    """Determine whether governed context establishes any fulfillment path for requested facts.

    This gate is provider-neutral and read-only. It becomes conclusive only after capability,
    evidence, and derivation context have all been supplied. It does not invent mappings or
    choose a provider; it only checks whether the governed planning context contains support
    for each requested fact.
    """

    required_context_views: tuple[str, ...] = (
        "capability_registry",
        "evidence_catalog",
        "derivation_registry",
    )

    def evaluate(
        self,
        *,
        intent: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> FulfillmentFeasibilityResult:
        requested = _requested_facts(intent)
        if not requested:
            return FulfillmentFeasibilityResult(conclusive=True, feasible=True)

        if any(not isinstance(context.get(view), Mapping) for view in self.required_context_views):
            return FulfillmentFeasibilityResult(conclusive=False, feasible=False)

        searchable = " ".join(
            _normalize(item)
            for view in self.required_context_views
            for item in _iter_strings(context[view])
            if str(item).strip()
        )

        unsupported = tuple(
            fact for fact in requested if _normalize(fact) not in searchable
        )
        if not unsupported:
            return FulfillmentFeasibilityResult(conclusive=True, feasible=True)

        summary = (
            "No currently registered governed capability, authoritative evidence context, "
            "or approved derivation establishes support for requested fact(s): "
            + ", ".join(unsupported)
        )
        return FulfillmentFeasibilityResult(
            conclusive=True,
            feasible=False,
            unsupported_facts=unsupported,
            summary=summary,
        )
PY

echo "WROTE: implementation/orchestrator/semantic_fulfillment_feasibility.py"

echo "========== SECTION 3: WIRE OPTIONAL GATE INTO BOUNDED PLANNING LOOP =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/semantic_intent_planning_loop.py")
text = path.read_text()

protocol_marker = '''class IntentPlanSufficiencyValidator(Protocol):\n    def validate(\n        self,\n        *,\n        intent: Mapping[str, Any],\n        plan: FulfillmentPlanCandidate,\n        context: Mapping[str, Any],\n    ) -> Any: ...\n\n\n'''
protocol_insert = protocol_marker + '''class IntentFulfillmentFeasibilityGate(Protocol):\n    def evaluate(\n        self,\n        *,\n        intent: Mapping[str, Any],\n        context: Mapping[str, Any],\n    ) -> Any: ...\n\n\n'''
if "class IntentFulfillmentFeasibilityGate(Protocol):" not in text:
    if protocol_marker not in text:
        raise SystemExit("plan sufficiency protocol marker not found")
    text = text.replace(protocol_marker, protocol_insert, 1)

field_marker = '''    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n    plan_validator: IntentPlanSufficiencyValidator | None = None\n'''
field_replacement = field_marker + '''    feasibility_gate: IntentFulfillmentFeasibilityGate | None = None\n'''
if "feasibility_gate: IntentFulfillmentFeasibilityGate | None" not in text:
    if field_marker not in text:
        raise SystemExit("planning loop field marker not found")
    text = text.replace(field_marker, field_replacement, 1)

rejection_marker = '''                        rejected_plan_signatures.add(signature)\n                        context["plan_validation"] = {\n'''
rejection_insert = '''                        rejected_plan_signatures.add(signature)\n                        if self.feasibility_gate is not None:\n                            feasibility = self.feasibility_gate.evaluate(\n                                intent=dict(intent),\n                                context=dict(context),\n                            )\n                            if bool(getattr(feasibility, "conclusive", False)) and not bool(\n                                getattr(feasibility, "feasible", False)\n                            ):\n                                trace.append(PlanningTraceEntry(iteration, "fulfillment_infeasible"))\n                                return IntentPlanningOutcome(\n                                    status="knowledge_gap",\n                                    plan=None,\n                                    gap_summary=str(\n                                        getattr(\n                                            feasibility,\n                                            "summary",\n                                            "no governed fulfillment path supports the original intent",\n                                        )\n                                    ),\n                                    trace=tuple(trace),\n                                    iterations_used=iteration,\n                                    context_requests_used=context_requests,\n                                )\n                        context["plan_validation"] = {\n'''
if "fulfillment_infeasible" not in text:
    if rejection_marker not in text:
        raise SystemExit("rejected plan marker not found")
    text = text.replace(rejection_marker, rejection_insert, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat > implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py <<'PY'
from orchestrator.semantic_fulfillment_feasibility import (
    GovernedSemanticFulfillmentFeasibilityGate,
)


def test_feasibility_is_not_conclusive_until_governed_views_are_present():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("special fact",)},
        context={"capability_registry": {"items": ()}},
    )
    assert result.conclusive is False


def test_feasibility_fails_closed_when_all_governed_views_lack_requested_fact():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("special fact",)},
        context={
            "capability_registry": {"items": ({"fact_hints": "hostname"},)},
            "evidence_catalog": {"items": ({"fact_hints": "operating system"},)},
            "derivation_registry": {"items": ({"relationship_id": "endpoint.belongs_to.organization"},)},
        },
    )
    assert result.conclusive is True
    assert result.feasible is False
    assert result.unsupported_facts == ("special fact",)
    assert "special fact" in str(result.summary)


def test_feasibility_remains_possible_when_governed_context_supports_requested_fact():
    result = GovernedSemanticFulfillmentFeasibilityGate().evaluate(
        intent={"requested_facts": ("processor model",)},
        context={
            "capability_registry": {"items": ({"fact_hints": "hostname,processor model"},)},
            "evidence_catalog": {"items": ()},
            "derivation_registry": {"items": ()},
        },
    )
    assert result.conclusive is True
    assert result.feasible is True
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py"

"$PY" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/tests/test_semantic_intent_planning_loop.py")
text = path.read_text()
if "test_infeasible_fulfillment_stops_rejected_plan_retry_loop" not in text:
    text += r'''


def test_infeasible_fulfillment_stops_rejected_plan_retry_loop():
    from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate
    from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(
                        FulfillmentPlanStepCandidate(
                            capability_name="endpoint.device.search",
                            purpose="attempt governed endpoint fact retrieval",
                            expected_evidence=("special fact",),
                        ),
                    ),
                    rationale_summary="candidate plan",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "items": ({"capability_name": "endpoint.device.search", "fact_hints": "hostname"},),
                    "capability_names": ("endpoint.device.search",),
                }
            if request.view == "evidence_catalog":
                return {"items": ({"fact_hints": "operating system"},)}
            if request.view == "derivation_registry":
                return {"items": ({"relationship_id": "endpoint.belongs_to.organization"},)}
            return {"items": ()}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(view="capability_registry"),
                PlanningContextRequest(view="evidence_catalog"),
                PlanningContextRequest(view="derivation_registry"),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=GovernedSemanticPlanSufficiencyValidator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
    ).plan(intent={"requested_facts": ("special fact",), "resource_type": "endpoint"})

    assert outcome.status == "knowledge_gap"
    assert outcome.iterations_used == 1
    assert [entry.status for entry in outcome.trace] == ["fulfillment_infeasible"]
    assert "special fact" in str(outcome.gap_summary)
'''
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: {path} already contains feasibility regression")
PY

echo "========== SECTION 5: ENABLE GATE IN LIVE OBSERVE-ONLY PROBE =========="
"$PY" - <<'PY'
from pathlib import Path
path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()
import_marker = "from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator\n"
new_import = import_marker + "from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate\n"
if "GovernedSemanticFulfillmentFeasibilityGate" not in text:
    if import_marker not in text:
        raise SystemExit("live probe sufficiency import marker not found")
    text = text.replace(import_marker, new_import, 1)

planner_marker = "    plan_validator=GovernedSemanticPlanSufficiencyValidator(),\n"
planner_replacement = planner_marker + "    feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),\n"
if "feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate()" not in text:
    if planner_marker not in text:
        raise SystemExit("live probe planner marker not found")
    text = text.replace(planner_marker, planner_replacement, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 6: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 7: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Governed semantic planning now stops retrying insufficient plans once capability, evidence, and derivation context conclusively establish that no governed fulfillment path supports the requested facts."
echo "The feasibility gate is provider-neutral, read-only, and does not invent provider mappings or derivations."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED SEMANTIC FULFILLMENT FEASIBILITY GATE =========="
