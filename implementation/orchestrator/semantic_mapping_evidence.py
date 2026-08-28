from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_mapping_registry import SemanticMappingRegistry


def _semantic_key(canonical_fact: str) -> str:
    return "_".join(
        token
        for token in "".join(
            character if character.isalnum() else " "
            for character in canonical_fact.casefold()
        ).split()
        if token
    )


@dataclass(frozen=True, slots=True)
class GovernedSemanticMappingEvidenceProjector:
    """Project approved provider fields into canonical semantic evidence.

    The projector does not search provider documentation, infer aliases, or invoke a
    provider. It only consumes already-approved semantic mappings and values that are
    actually present in the returned provider record.

    Provider API mechanics remain connector-owned. Semantic meaning remains registry-
    owned. Missing or ambiguous mappings fail closed.
    """

    registry: SemanticMappingRegistry

    def project(
        self,
        *,
        provider_id: str,
        capability_name: str,
        data: Any,
        requested_facts: tuple[str, ...],
    ) -> Any:
        if not isinstance(data, Mapping):
            return data

        raw_provider_data = data.get("provider_data")
        if not isinstance(raw_provider_data, Mapping):
            return data

        projected_provider_data = dict(raw_provider_data)

        existing_semantic = projected_provider_data.get("semantic_evidence")
        if existing_semantic is None:
            semantic_root: dict[str, Any] = {}
        elif isinstance(existing_semantic, Mapping):
            semantic_root = dict(existing_semantic)
        else:
            raise ValueError(
                "provider semantic_evidence must be an object when present"
            )

        projected_any = False

        for canonical_fact in requested_facts:
            mappings = self.registry.find_active(
                canonical_fact=canonical_fact,
                provider_id=provider_id,
            )

            mappings = tuple(
                mapping
                for mapping in mappings
                if capability_name in mapping.capability_names
            )

            if not mappings:
                continue

            if len(mappings) != 1:
                raise LookupError(
                    "approved semantic mapping resolution is ambiguous for "
                    f"{canonical_fact}"
                )

            mapping = mappings[0]

            # Provider-schema approval allows only the explicitly approved field.
            # Do not recursively hunt through unrelated nested provider objects.
            if mapping.provider_field not in raw_provider_data:
                continue

            value = raw_provider_data[mapping.provider_field]

            if value is None:
                continue

            key = _semantic_key(mapping.canonical_fact)

            if key in semantic_root and semantic_root[key] != value:
                raise LookupError(
                    "existing semantic evidence conflicts with approved mapping"
                )

            semantic_root[key] = value
            projected_any = True

        if not projected_any:
            return data

        projected_provider_data["semantic_evidence"] = semantic_root

        projected = dict(data)
        projected["provider_data"] = projected_provider_data
        return projected
