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
