from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .relationship_registry import SQLiteCanonicalRelationshipRegistry
from .relationships import CanonicalRelationship, RelationshipState, ResourceRef


class RelationshipTraversalDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class CanonicalRelationshipQuery:
    organization_id: str
    resource: ResourceRef
    relationship_types: frozenset[str] | None = None
    states: frozenset[RelationshipState] = frozenset({RelationshipState.ACTIVE})
    direction: RelationshipTraversalDirection = RelationshipTraversalDirection.BOTH
    limit: int = 100

    def validate(self) -> None:
        if not self.organization_id.strip():
            raise ValueError("relationship query organization_id is required")
        if self.resource.organization_id != self.organization_id:
            raise PermissionError("relationship query resource organization mismatch")
        if self.relationship_types is not None and not self.relationship_types:
            raise ValueError("relationship query relationship_types cannot be empty")
        if not self.states:
            raise ValueError("relationship query states cannot be empty")
        if not 1 <= self.limit <= 500:
            raise ValueError("relationship query limit must be between 1 and 500")


@dataclass(frozen=True, slots=True)
class RelationshipTraversalResult:
    relationship: CanonicalRelationship
    matched_resource: ResourceRef
    related_resource: ResourceRef
    direction: RelationshipTraversalDirection


class CanonicalRelationshipQueryService:
    """Tenant-scoped read/traversal boundary over the canonical registry.

    The service only returns registry-backed relationships in explicitly allowed
    lifecycle states. It cannot promote evidence, mutate lifecycle state, or grant
    identity, capability, approval, provider, or execution authority.
    """

    def __init__(self, registry: SQLiteCanonicalRelationshipRegistry) -> None:
        self._registry = registry

    def get(
        self,
        relationship_id: str,
        *,
        organization_id: str,
        allowed_states: Iterable[RelationshipState] = (RelationshipState.ACTIVE,),
    ) -> CanonicalRelationship | None:
        if not relationship_id.strip() or not organization_id.strip():
            raise ValueError("relationship query identifiers are required")
        states = frozenset(allowed_states)
        if not states:
            raise ValueError("relationship query allowed_states cannot be empty")
        relationship = self._registry.get(relationship_id, organization_id=organization_id)
        if relationship is None or relationship.state not in states:
            return None
        return relationship

    def traverse(self, query: CanonicalRelationshipQuery) -> tuple[RelationshipTraversalResult, ...]:
        query.validate()
        relationships = self._registry.list_for_organization(
            query.organization_id,
            states=query.states,
        )
        results: list[RelationshipTraversalResult] = []
        for relationship in relationships:
            if query.relationship_types is not None:
                if relationship.relationship_type not in query.relationship_types:
                    continue

            source_matches = self._same_resource(relationship.source, query.resource)
            target_matches = self._same_resource(relationship.target, query.resource)

            if query.direction in {RelationshipTraversalDirection.OUTBOUND, RelationshipTraversalDirection.BOTH} and source_matches:
                results.append(
                    RelationshipTraversalResult(
                        relationship=relationship,
                        matched_resource=relationship.source,
                        related_resource=relationship.target,
                        direction=RelationshipTraversalDirection.OUTBOUND,
                    )
                )
            if query.direction in {RelationshipTraversalDirection.INBOUND, RelationshipTraversalDirection.BOTH} and target_matches:
                results.append(
                    RelationshipTraversalResult(
                        relationship=relationship,
                        matched_resource=relationship.target,
                        related_resource=relationship.source,
                        direction=RelationshipTraversalDirection.INBOUND,
                    )
                )
            if len(results) >= query.limit:
                break
        return tuple(results)

    @staticmethod
    def _same_resource(left: ResourceRef, right: ResourceRef) -> bool:
        return (
            left.organization_id == right.organization_id
            and left.provider == right.provider
            and left.resource_type == right.resource_type
            and left.external_id == right.external_id
            and left.tenant_id == right.tenant_id
        )
