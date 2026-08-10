from dataclasses import replace
from datetime import datetime, timezone

import pytest

from connectors.core.relationship_registry import CanonicalRelationshipRegistryError, SQLiteCanonicalRelationshipRegistry
from connectors.core.relationships import CanonicalRelationship, RelationshipState, ResourceRef, VerificationState


def relationship(relationship_id: str = "rel-1", *, organization_id: str = "org-1") -> CanonicalRelationship:
    return CanonicalRelationship(
        relationship_id=relationship_id,
        relationship_type="represents",
        source=ResourceRef("microsoft_graph", "user", "user-1", organization_id),
        target=ResourceRef("autotask", "contact", "contact-1", organization_id),
        state=RelationshipState.ACTIVE,
        verification=VerificationState.VERIFIED,
        confidence=1.0,
        established_by="central-orchestrator",
        provenance=("provider:jason_resource_convergence", "promotion-policy:rel@1"),
        effective_at=datetime(2026, 8, 9, 20, 0, tzinfo=timezone.utc),
    )


def test_register_get_and_history_survive_restart(tmp_path) -> None:
    path = tmp_path / "relationships.sqlite3"
    first = SQLiteCanonicalRelationshipRegistry(path)
    first.register(relationship(), changed_by="orchestrator", reason="policy admitted")

    second = SQLiteCanonicalRelationshipRegistry(path)
    stored = second.get("rel-1", organization_id="org-1")
    assert stored == relationship()
    history = second.history("rel-1", organization_id="org-1")
    assert len(history) == 1
    assert history[0].previous_state is None
    assert history[0].new_state is RelationshipState.ACTIVE


def test_exact_duplicate_register_is_idempotent(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    item = relationship()
    registry.register(item, changed_by="orchestrator", reason="first")
    registry.register(item, changed_by="orchestrator", reason="duplicate delivery")
    assert len(registry.history("rel-1", organization_id="org-1")) == 1


def test_conflicting_relationship_id_reuse_fails_closed(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    original = relationship()
    registry.register(original, changed_by="orchestrator", reason="first")
    conflicting = replace(original, relationship_type="maps_to")
    with pytest.raises(CanonicalRelationshipRegistryError, match="conflicting"):
        registry.register(conflicting, changed_by="orchestrator", reason="collision")


def test_cross_organization_read_fails_closed(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    registry.register(relationship(), changed_by="orchestrator", reason="first")
    with pytest.raises(PermissionError, match="organization mismatch"):
        registry.get("rel-1", organization_id="org-2")


def test_lifecycle_transition_preserves_payload_provenance(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    registry.register(relationship(), changed_by="orchestrator", reason="first")
    registry.transition(
        "rel-1",
        organization_id="org-1",
        new_state=RelationshipState.SUSPENDED,
        changed_by="policy-gate",
        reason="provider evidence disputed",
    )
    stored = registry.get("rel-1", organization_id="org-1")
    assert stored is not None
    assert stored.state is RelationshipState.SUSPENDED
    assert stored.provenance == relationship().provenance
    history = registry.history("rel-1", organization_id="org-1")
    assert [event.new_state for event in history] == [RelationshipState.ACTIVE, RelationshipState.SUSPENDED]


def test_invalid_lifecycle_transition_fails_closed(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    registry.register(relationship(), changed_by="orchestrator", reason="first")
    registry.transition(
        "rel-1",
        organization_id="org-1",
        new_state=RelationshipState.REVOKED,
        changed_by="policy-gate",
        reason="authority revoked",
    )
    with pytest.raises(PermissionError, match="transition denied"):
        registry.transition(
            "rel-1",
            organization_id="org-1",
            new_state=RelationshipState.ACTIVE,
            changed_by="operator",
            reason="unsafe reactivation",
        )


def test_supersession_uses_new_relationship_id_and_records_old_state(tmp_path) -> None:
    registry = SQLiteCanonicalRelationshipRegistry(tmp_path / "relationships.sqlite3")
    registry.register(relationship(), changed_by="orchestrator", reason="first")
    replacement = relationship("rel-2")
    registry.supersede(
        "rel-1",
        replacement,
        organization_id="org-1",
        changed_by="orchestrator",
        reason="new authoritative mapping",
    )
    assert registry.get("rel-1", organization_id="org-1").state is RelationshipState.SUPERSEDED
    assert registry.get("rel-2", organization_id="org-1").state is RelationshipState.ACTIVE
