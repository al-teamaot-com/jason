#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START GOVERNED SEMANTIC PLAN SUFFICIENCY VALIDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ADD PROVIDER-NEUTRAL PLAN SUFFICIENCY VALIDATOR =========="
cat > implementation/orchestrator/semantic_plan_sufficiency.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_intent_planning_loop import FulfillmentPlanCandidate


def _normalize(value: str) -> str:
    return " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )


def _facts_from_intent(intent: Mapping[str, Any]) -> tuple[str, ...]:
    raw = intent.get("requested_facts", ())
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, (list, tuple, set, frozenset)):
        values = tuple(str(item) for item in raw)
    else:
        values = ()
    return tuple(item.strip() for item in values if item.strip())


def _fact_hints(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw = str(item.get("fact_hints", ""))
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class PlanSufficiencyResult:
    sufficient: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernedSemanticPlanSufficiencyValidator:
    """Validate a proposed plan against the original intent and governed capability facts.

    A reasoner cannot make a plan sufficient merely by asserting expected evidence. At least
    one selected governed capability must advertise each requested fact in capability-registry
    context. Unknown support fails closed so the reasoner can seek another governed capability,
    evidence source, derivation, or declare a knowledge gap.
    """

    def validate(
        self,
        *,
        intent: Mapping[str, Any],
        plan: FulfillmentPlanCandidate,
        context: Mapping[str, Any],
    ) -> PlanSufficiencyResult:
        requested = _facts_from_intent(intent)
        if not requested:
            return PlanSufficiencyResult(sufficient=True)

        snapshot = context.get("capability_registry")
        if not isinstance(snapshot, Mapping):
            return PlanSufficiencyResult(
                sufficient=False,
                issues=("governed capability-registry context is unavailable",),
            )

        raw_items = snapshot.get("items", ())
        if not isinstance(raw_items, (list, tuple)):
            return PlanSufficiencyResult(
                sufficient=False,
                issues=("governed capability-registry context has no inspectable capability records",),
            )

        by_name = {
            str(item.get("capability_name", "")).strip(): item
            for item in raw_items
            if isinstance(item, Mapping) and str(item.get("capability_name", "")).strip()
        }
        selected = tuple(by_name.get(step.capability_name) for step in plan.steps)
        selected = tuple(item for item in selected if isinstance(item, Mapping))

        issues: list[str] = []
        for requested_fact in requested:
            normalized_requested = _normalize(requested_fact)
            supported = False
            for capability in selected:
                hints = {_normalize(item) for item in _fact_hints(capability)}
                if normalized_requested in hints:
                    supported = True
                    break
            if not supported:
                issues.append(
                    f"no selected governed capability advertises requested fact: {requested_fact}"
                )

        return PlanSufficiencyResult(sufficient=not issues, issues=tuple(issues))
PY

echo "WROTE: implementation/orchestrator/semantic_plan_sufficiency.py"

echo "========== SECTION 3: WIRE OPTIONAL VALIDATOR INTO BOUNDED PLANNING LOOP =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/semantic_intent_planning_loop.py')
text = path.read_text()

old = '''class IntentPlanningContextBootstrapper(Protocol):\n    def requests_for(\n        self,\n        *,\n        intent: Mapping[str, Any],\n    ) -> Sequence[PlanningContextRequest]: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
new = '''class IntentPlanningContextBootstrapper(Protocol):\n    def requests_for(\n        self,\n        *,\n        intent: Mapping[str, Any],\n    ) -> Sequence[PlanningContextRequest]: ...\n\n\nclass IntentPlanSufficiencyValidator(Protocol):\n    def validate(\n        self,\n        *,\n        intent: Mapping[str, Any],\n        plan: FulfillmentPlanCandidate,\n        context: Mapping[str, Any],\n    ) -> Any: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n'''
if old not in text:
    raise SystemExit('validator protocol insertion marker not found')
text = text.replace(old, new, 1)

old = '''    budget: IntentPlanningBudget = IntentPlanningBudget()\n    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n'''
new = '''    budget: IntentPlanningBudget = IntentPlanningBudget()\n    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n    plan_validator: IntentPlanSufficiencyValidator | None = None\n'''
if old not in text:
    raise SystemExit('planner field insertion marker not found')
text = text.replace(old, new, 1)

old = '''        satisfied_requests: set[tuple[str, str]] = set()\n\n        if self.context_bootstrapper is not None:\n'''
new = '''        satisfied_requests: set[tuple[str, str]] = set()\n        rejected_plan_signatures: set[str] = set()\n\n        if self.context_bootstrapper is not None:\n'''
if old not in text:
    raise SystemExit('rejected signature initialization marker not found')
text = text.replace(old, new, 1)

old = '''            if turn.status == "propose_plan":\n                assert turn.plan is not None\n                _validate_plan_against_governed_capabilities(turn.plan, context)\n                trace.append(PlanningTraceEntry(iteration, turn.status))\n                return IntentPlanningOutcome(\n                    status="planned",\n                    plan=turn.plan,\n                    gap_summary=None,\n                    trace=tuple(trace),\n                    iterations_used=iteration,\n                    context_requests_used=context_requests,\n                )\n'''
new = '''            if turn.status == "propose_plan":\n                assert turn.plan is not None\n                _validate_plan_against_governed_capabilities(turn.plan, context)\n                if self.plan_validator is not None:\n                    validation = self.plan_validator.validate(\n                        intent=dict(intent),\n                        plan=turn.plan,\n                        context=dict(context),\n                    )\n                    if not bool(getattr(validation, "sufficient", False)):\n                        issues = tuple(str(item) for item in getattr(validation, "issues", ()))\n                        signature = repr((turn.plan.steps, turn.plan.unresolved_requirements, issues))\n                        if signature in rejected_plan_signatures:\n                            trace.append(PlanningTraceEntry(iteration, "plan_rejected"))\n                            return IntentPlanningOutcome(\n                                status="knowledge_gap",\n                                plan=None,\n                                gap_summary=(\n                                    "planning reasoner repeated a plan that did not satisfy the original intent"\n                                ),\n                                trace=tuple(trace),\n                                iterations_used=iteration,\n                                context_requests_used=context_requests,\n                            )\n                        rejected_plan_signatures.add(signature)\n                        context["plan_validation"] = {\n                            "sufficient": False,\n                            "issues": issues,\n                            "instruction": (\n                                "Revise the plan using governed context, request different governed context, "\n                                "or declare a knowledge gap. Do not repeat the rejected plan."\n                            ),\n                        }\n                        trace.append(PlanningTraceEntry(iteration, "plan_rejected"))\n                        continue\n                trace.append(PlanningTraceEntry(iteration, turn.status))\n                return IntentPlanningOutcome(\n                    status="planned",\n                    plan=turn.plan,\n                    gap_summary=None,\n                    trace=tuple(trace),\n                    iterations_used=iteration,\n                    context_requests_used=context_requests,\n                )\n'''
if old not in text:
    raise SystemExit('plan validation insertion marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 4: GUIDE OLLAMA REASONER TO CONSUME PLAN VALIDATION =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()
old = '''                "Prefer direct authoritative evidence; otherwise consider alternate governed capabilities or "\n                "approved derivations represented in context. If no governed fulfillment path is established, "\n                "declare a knowledge gap. Keep reasoning concise and structured."\n'''
new = '''                "Prefer direct authoritative evidence; otherwise consider alternate governed capabilities or "\n                "approved derivations represented in context. If plan_validation context is present, the prior "\n                "plan was rejected as insufficient for the original intent: consume those issues, revise the "\n                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "\n                "plan unchanged. If no governed fulfillment path is established, declare a knowledge gap. Keep "\n                "reasoning concise and structured."\n'''
if old not in text:
    raise SystemExit('Ollama plan-validation prompt marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 5: ADD GENERALIZED TEST COVERAGE =========="
cat > implementation/orchestrator/tests/test_semantic_plan_sufficiency.py <<'PY'
from orchestrator.semantic_intent_planning_loop import (
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
)
from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator


def plan(*, expected_evidence=("operating system display version",)):
    return FulfillmentPlanCandidate(
        steps=(
            FulfillmentPlanStepCandidate(
                capability_name="endpoint.device.search",
                purpose="retrieve governed endpoint facts",
                required_facts=("hostname", "operating system"),
                expected_evidence=expected_evidence,
            ),
        ),
        rationale_summary="use governed endpoint discovery",
    )


def context(*fact_hints):
    return {
        "capability_registry": {
            "capability_names": ("endpoint.device.search",),
            "items": (
                {
                    "capability_name": "endpoint.device.search",
                    "fact_hints": ",".join(fact_hints),
                },
            ),
        }
    }


def test_expected_evidence_claim_does_not_make_unsupported_fact_sufficient():
    result = GovernedSemanticPlanSufficiencyValidator().validate(
        intent={"requested_facts": ("operating system display version",)},
        plan=plan(),
        context=context("hostname", "operating system"),
    )
    assert result.sufficient is False
    assert result.issues == (
        "no selected governed capability advertises requested fact: operating system display version",
    )


def test_selected_governed_capability_must_advertise_requested_fact():
    result = GovernedSemanticPlanSufficiencyValidator().validate(
        intent={"requested_facts": ("processor model",)},
        plan=plan(expected_evidence=("processor model",)),
        context=context("hostname", "processor model", "total memory"),
    )
    assert result.sufficient is True
    assert result.issues == ()
PY

cat >> implementation/orchestrator/tests/test_semantic_intent_planning_loop.py <<'PY'


def test_insufficient_plan_is_returned_to_reasoner_for_revision():
    from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator

    class Reasoner:
        def __init__(self):
            self.calls = 0

        def next_turn(self, *, intent, context, history):
            self.calls += 1
            if self.calls == 1:
                return PlanningTurn(
                    status="propose_plan",
                    plan=FulfillmentPlanCandidate(
                        steps=(
                            FulfillmentPlanStepCandidate(
                                capability_name="endpoint.device.search",
                                purpose="read endpoint",
                                expected_evidence=("special fact",),
                            ),
                        ),
                        rationale_summary="candidate plan",
                    ),
                )
            assert context["plan_validation"]["sufficient"] is False
            return PlanningTurn(status="declare_gap", gap_summary="no governed capability supports special fact")

    class Reader:
        def read(self, *, request, intent):
            return {
                "view_name": request.view,
                "items": (
                    {
                        "capability_name": "endpoint.device.search",
                        "fact_hints": "hostname,operating system",
                    },
                ),
                "capability_names": ("endpoint.device.search",),
                "authoritative": True,
                "truncated": False,
            }

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(
                    view="capability_registry",
                    query={"query": "endpoint"},
                    purpose="bootstrap governed capabilities",
                ),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=GovernedSemanticPlanSufficiencyValidator(),
    ).plan(intent={"requested_facts": ("special fact",), "resource_type": "endpoint"})

    assert outcome.status == "knowledge_gap"
    assert outcome.iterations_used == 2
    assert [entry.status for entry in outcome.trace] == ["plan_rejected", "declare_gap"]
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_plan_sufficiency.py"
echo "UPDATED: implementation/orchestrator/tests/test_semantic_intent_planning_loop.py"

echo "========== SECTION 6: ENABLE VALIDATION IN LIVE OBSERVE-ONLY PROBE =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('scripts/run-live-observe-only-semantic-planner-intent-probe.sh')
text = path.read_text()
old = 'from orchestrator.semantic_planning_bootstrap import ProviderNeutralIntentContextBootstrapper\n'
new = old + 'from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator\n'
if old not in text:
    raise SystemExit('live probe validator import marker not found')
if 'GovernedSemanticPlanSufficiencyValidator' not in text:
    text = text.replace(old, new, 1)

old = '''    context_bootstrapper=ProviderNeutralIntentContextBootstrapper(),\n)\n'''
new = '''    context_bootstrapper=ProviderNeutralIntentContextBootstrapper(),\n    plan_validator=GovernedSemanticPlanSufficiencyValidator(),\n)\n'''
if old not in text:
    raise SystemExit('live probe validator wiring marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 7: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 8: FOCUSED TESTS ==========" 
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 9: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "Governed semantic planning now validates proposed plan sufficiency against the original requested facts and selected governed capability metadata."
echo "A reasoner assertion of expected evidence cannot by itself make an unsupported plan sufficient."
echo "Insufficient plans are returned to the bounded reasoner for revision or a governed knowledge gap."
echo "This is provider-neutral and does not special-case Windows, Datto, or the current acceptance question."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED SEMANTIC PLAN SUFFICIENCY VALIDATION =========="
