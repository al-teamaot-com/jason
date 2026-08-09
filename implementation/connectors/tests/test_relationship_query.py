from datetime import datetime, timezone

import pytest

from connectors.core.relationship_query import (
    CanonicalRelationshipQuery,
    CanonicalRelationshipQueryService,
    RelationshipTraversalDirection,
)
from connectors.core.relationship_registry import SQLiteCanonicalRelationshipRegistry
from connectors.core.relationships import (
    CanonicalRelationship,
    RelationshipState,
    ResourceRef,
    VerificationState,
)


def ref(provider: str, resource_type: str, external_id: str, organization_id: str = "org-1") -> ResourceRef:
    return ResourceRef(
        provider=provider,
        resource_type=resource_type,
        external_id=external_id,
        organization_id=organization_id,
    )


def relationship(
    relationship_id: str,
    source: ResourceRef,
    target: ResourceRef,
    *,
    state: RelationshipState = RelationshipState.ACTIVE,
    relationship_type: str = "represents",
) -> CanonicalRelationship:
    return CanonicalRelationship(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        source=source,
        target=target,
        state=state,
        verification=VerificationState.VERIFIED,
        confidence=1.0,
        established_by="central-orchestrator",
        provenance=("promotion-policy:test@1",),
        effective_at=datetime.now(timezone.utc),
    )


def test_traverses_active_relationships_in_both_directions(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.db")
    device = ref("datto_rmm", "device", "device-1")
    configuration = ref("it_glue", "configuration", "config-1")
    company = ref("autotask", "company", "company-1")
    registry.register(relationship("rel-1", configuration, device), changed_by="test", reason="seed")
    registry.register(relationship("rel-2", device, company, relationship_type="belongs_to"), changed_by="test", reason="seed")

    service = CanonicalRelationshipQueryService(registry)
    results = service.traverse(CanonicalRelationshipQuery(organization_id="org-1", resource=device))

    assert {(result.relationship.relationship_id, result.direction) for result in results} == {
        ("rel-1", RelationshipTraversalDirection.INBOUND),
        ("rel-2", RelationshipTraversalDirection.OUTBOUND),
    }


def test_default_query_hides_non_active_relationships(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.db")
    source = ref("microsoft_graph", "user", "user-1")
    target = ref("autotask", "contact", "contact-1")
    registry.register(relationship("rel-1", source, target), changed_by="test", reason="seed")
    registry.transition(
        "rel-1",
        organization_id="org-1",
        new_state=RelationshipState.REVOKED,
        changed_by="test",
        reason="revoked",
    )

    service = CanonicalRelationshipQueryService(registry)
    assert service.get("rel-1", organization_id="org-1") is None
    assert service.traverse(CanonicalRelationshipQuery(organization_id="org-1", resource=source)) == ()


def test_explicit_state_query_can_read_revoked_relationship_for_evidence(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.db")
    source = ref("microsoft_graph", "user", "user-1")
    target = ref("autotask", "contact", "contact-1")
    registry.register(relationship("rel-1", source, target), changed_by="test", reason="seed")
    registry.transition(
        "rel-1",
        organization_id="org-1",
        new_state=RelationshipState.REVOKED,
        changed_by="test",
        reason="revoked",
    )

    service = CanonicalRelationshipQueryService(registry)
    result = service.get(
        "rel-1",
        organization_id="org-1",
        allowed_states=(RelationshipState.REVOKED,),
    )
    assert result is not None
    assert result.state is RelationshipState.REVOKED


def test_cross_organization_query_fails_closed(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.db")
    service = CanonicalRelationshipQueryService(registry)

    with pytest.raises(PermissionError, match="organization mismatch"):
        service.traverse(
            CanonicalRelationshipQuery(
                organization_id="org-1",
                resource=ref("datto_rmm", "device", "device-1", organization_id="org-2"),
            )
        )


def test_query_can_filter_relationship_type_and_direction(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.db")
    device = ref("datto_rmm", "device", "device-1")
    company = ref("autotask", "company", "company-1")
    configuration = ref("it_glue", "configuration", "config-1")
    registry.register(relationship("rel-1", device, company, relationship_type="belongs_to"), changed_by="test", reason="seed")
    registry.register(relationship("rel-2", configuration, device), changed_by="test", reason="seed")

    service = CanonicalRelationshipQueryService(registry)
    results = service.traverse(
        CanonicalRelationshipQuery(
            organization_id="org-1",
            resource=device,
            relationship_types=frozenset({"belongs_to"}),
            direction=RelationshipTraversalDirection.OUTBOUND,
        )
    )

    assert len(results) == 1
    assert results[0].relationship.relationship_id == "rel-1"
    assert results[0].related_resource == company
