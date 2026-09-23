from __future__ import annotations

from typing import Mapping

from .semantic_fact_resolver import SemanticFactResolution


def _normalized_scope(value: str) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def semantic_resolution_matches_resource_contract(
    *,
    resolution: SemanticFactResolution,
    metadata: Mapping[str, str],
) -> bool:
    """Match governed semantic knowledge to a capability's resource contract.

    This deliberately does not map human phrases, canonical fact labels, provider
    fields, or providers to capabilities. It uses only two already-governed pieces
    of structural truth:

    - the semantic concept namespace / evidence contexts; and
    - the capability's provider-neutral ``resource_types`` contract.

    A semantic fact such as ``endpoint.ip_address`` or ``endpoint.last_seen`` can
    therefore be recognized as belonging to an endpoint read capability without a
    question-specific fact list. Sensitive concepts in another semantic domain do
    not become endpoint-readable merely because the human mentioned an endpoint.
    """

    if resolution.source != "semantic_knowledge_registry":
        return False

    concept_id = str(resolution.concept_id or "").strip()
    if not concept_id:
        return False

    resource_types = {
        _normalized_scope(item)
        for item in str(metadata.get("resource_types", "")).split(",")
        if str(item).strip()
    }
    if not resource_types:
        return False

    concept_namespace = _normalized_scope(concept_id.split(".", 1)[0])
    semantic_scopes = {concept_namespace}
    semantic_scopes.update(
        _normalized_scope(item)
        for item in resolution.evidence_contexts
        if str(item).strip()
    )

    return bool(resource_types.intersection(semantic_scopes))
