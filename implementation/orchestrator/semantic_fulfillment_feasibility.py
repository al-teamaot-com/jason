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
