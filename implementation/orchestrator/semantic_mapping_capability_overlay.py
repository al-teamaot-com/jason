from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .semantic_mapping_registry import SemanticMappingRegistry


def _split_hints(value: object) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


@dataclass(frozen=True, slots=True)
class GovernedSemanticMappingCapabilityOverlay:
    registry: SemanticMappingRegistry

    def apply(
        self,
        *,
        capability_records: Sequence[Mapping[str, object]],
    ) -> tuple[Mapping[str, object], ...]:
        overlays: dict[str, list[Mapping[str, object]]] = {}

        for mapping in self.registry.as_context():
            for capability_name in mapping["capability_names"]:
                overlays.setdefault(
                    str(capability_name),
                    [],
                ).append(mapping)

        results: list[Mapping[str, object]] = []

        for record in capability_records:
            updated = dict(record)

            capability_name = str(
                updated.get("capability_name", "")
            ).strip()

            mappings = overlays.get(capability_name, [])

            if mappings:
                hints = _split_hints(updated.get("fact_hints"))

                derived_facts: list[str] = []

                for mapping in mappings:
                    fact = str(mapping["canonical_fact"]).strip()

                    if fact and fact.casefold() not in {
                        item.casefold() for item in hints
                    }:
                        hints.append(fact)

                    if fact:
                        derived_facts.append(fact)

                updated["fact_hints"] = ",".join(hints)
                updated["approved_semantic_mapping_facts"] = tuple(
                    sorted(set(derived_facts))
                )
                updated["semantic_mapping_source"] = (
                    "approved_semantic_mapping_registry"
                )

            results.append(updated)

        return tuple(results)
