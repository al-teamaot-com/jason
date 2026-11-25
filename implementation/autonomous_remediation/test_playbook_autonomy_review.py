from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from connectors.src.jason_connectors.approval_requests import AcceptedApproval

from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore
from .playbook_autonomy_review import (
    PlaybookAutonomyReviewError,
    PlaybookAutonomyReviewService,
)
from .playbook_autonomy_scope import registered_autonomy_scope

NOW = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


def registry(tmp_path, *, version="1.0.0", capabilities=None):
    caps = capabilities or ["service.ticket.note.create", "service.ticket.update"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "playbooks": [{
            "id": "demo",
            "name": "Demo Playbook",
            "version": version,
            "lifecycle": "production",
            "enabled": True,
            "source": "docs/playbooks/demo.md",
            "review_status": "diagnostic_autonomous_cleanup_gated",
            "autonomy": {
                "activation": "autonomous",
                "required_gates": ["identity"],
                "allowed_capabilities": caps,
                "policy_id": "playbook-autonomy:demo",
            },
        }],
    }), encoding="utf-8")
    return path


def accepted(request, *, actor="person-owner", status="approved"):
    return AcceptedApproval(
        approval_id=request.approval_id,
        request_id=request.request_id,
        capability=request.capability,
        organization_id=request.organization_id,
        client_id=None,
        requested_by=request.requested_by,
        status=status,
        decided_by=actor,
        decided_at=NOW + timedelta(minutes=1),
        expires_at=request.expires_at,
        channel="microsoft_teams",
        channel_response_id="teams-message-1",
        evidence_references=request.evidence_references,
    )


def test_owner_approval_mechanically_promotes_exact_reviewed_scope(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    service = PlaybookAutonomyReviewService(
        registry_path=registry(tmp_path),
        promotion_store=store,
        owner_identity_ids=frozenset({"person-owner"}),
        audit_path=tmp_path / "audit.jsonl",
    )
    request = service.build_request(
        playbook_id="demo", requested_by="person-tech", now=NOW,
        approval_id="pbautreq-1", request_id="req-1", correlation_id="corr-1",
    )
    result = service.promote_accepted(request=request, accepted=accepted(request))
    assert result.created is True
    assert result.promotion.approved_by == "person-owner"
    assert result.promotion.playbook_id == "demo"
    assert result.promotion.allowed_capabilities == (
        "service.ticket.note.create", "service.ticket.update"
    )
    facts = dict(request.presentation.facts)
    assert "Scope fingerprint" in facts
    assert facts["Authority envelope"] == result.scope.authority_envelope_sha256
    assert result.promotion.authority_envelope_sha256 == result.scope.authority_envelope_sha256
    assert store.find_scope_approved(
        playbook_id="demo", playbook_version="1.0.0",
        policy_id="playbook-autonomy:demo",
        required_capabilities=result.scope.allowed_capabilities,
    ) is not None


def test_technician_cannot_be_substituted_as_owner(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    service = PlaybookAutonomyReviewService(
        registry_path=registry(tmp_path), promotion_store=store,
        owner_identity_ids=frozenset({"person-owner"}),
    )
    request = service.build_request(playbook_id="demo", requested_by="person-tech", now=NOW)
    with pytest.raises(PlaybookAutonomyReviewError, match="OWNER_REQUIRED"):
        service.promote_accepted(request=request, accepted=accepted(request, actor="person-tech"))


def test_registry_change_after_card_generation_fails_closed(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    path = registry(tmp_path)
    service = PlaybookAutonomyReviewService(
        registry_path=path, promotion_store=store,
        owner_identity_ids=frozenset({"person-owner"}),
    )
    request = service.build_request(playbook_id="demo", requested_by="person-tech", now=NOW)
    registry(tmp_path, version="1.0.1")
    with pytest.raises(PlaybookAutonomyReviewError, match="VERSION_DRIFT|FINGERPRINT_DRIFT"):
        service.promote_accepted(request=request, accepted=accepted(request))
    assert store.list_all() == ()


def test_request_changes_never_promotes(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    service = PlaybookAutonomyReviewService(
        registry_path=registry(tmp_path), promotion_store=store,
        owner_identity_ids=frozenset({"person-owner"}),
    )
    request = service.build_request(playbook_id="demo", requested_by="person-tech", now=NOW)
    with pytest.raises(PlaybookAutonomyReviewError, match="OWNER_APPROVAL_REQUIRED"):
        service.promote_accepted(
            request=request,
            accepted=accepted(request, status="changes_requested"),
        )
    assert store.list_all() == ()


def test_authority_envelope_is_stable_for_version_only_and_changes_for_scope_change(tmp_path):
    path = registry(tmp_path, version="1.0.0")
    first = registered_autonomy_scope(registry_path=path, playbook_id="demo")
    registry(tmp_path, version="1.0.1")
    second = registered_autonomy_scope(registry_path=path, playbook_id="demo")
    assert first.entry_sha256 != second.entry_sha256
    assert first.authority_envelope_sha256 == second.authority_envelope_sha256

    registry(
        tmp_path,
        version="1.0.1",
        capabilities=["service.ticket.note.create", "service.ticket.update", "automation.component.execute"],
    )
    expanded = registered_autonomy_scope(registry_path=path, playbook_id="demo")
    assert expanded.authority_envelope_sha256 != first.authority_envelope_sha256


def test_derived_exact_version_requires_active_matching_envelope_root(tmp_path):
    path = registry(tmp_path, version="1.0.0")
    scope = registered_autonomy_scope(registry_path=path, playbook_id="demo")
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    root = store.new(
        playbook_id=scope.playbook_id,
        playbook_version=scope.playbook_version,
        policy_id=scope.policy_id,
        allowed_capabilities=scope.allowed_capabilities,
        approved_by="person-owner",
        authority_envelope_sha256=scope.authority_envelope_sha256,
    )
    store.put(root)
    derived = store.derive_exact_version_from_envelope(
        root=root,
        playbook_version="1.0.1",
        required_capabilities=scope.allowed_capabilities,
        authority_envelope_sha256=scope.authority_envelope_sha256,
        now=NOW,
    )
    assert derived.playbook_version == "1.0.1"
    assert derived.inherited_from_approval_id == root.approval_id
    assert store.find_scope_approved(
        playbook_id="demo",
        playbook_version="1.0.1",
        policy_id=scope.policy_id,
        required_capabilities=scope.allowed_capabilities,
        now=NOW,
    ) == derived

    store.revoke(root.approval_id, revoked_by="person-owner", reason="test revoke")
    assert store.find_scope_approved(
        playbook_id="demo",
        playbook_version="1.0.1",
        policy_id=scope.policy_id,
        required_capabilities=scope.allowed_capabilities,
        now=NOW,
    ) is None


def test_envelope_cannot_derive_expanded_capabilities(tmp_path):
    path = registry(tmp_path, version="1.0.0", capabilities=["service.ticket.note.create"])
    scope = registered_autonomy_scope(registry_path=path, playbook_id="demo")
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    root = store.new(
        playbook_id=scope.playbook_id,
        playbook_version=scope.playbook_version,
        policy_id=scope.policy_id,
        allowed_capabilities=scope.allowed_capabilities,
        approved_by="person-owner",
        authority_envelope_sha256=scope.authority_envelope_sha256,
    )
    store.put(root)
    with pytest.raises(ValueError, match="does not authorize"):
        store.derive_exact_version_from_envelope(
            root=root,
            playbook_version="1.0.1",
            required_capabilities=("service.ticket.note.create", "service.ticket.update"),
            authority_envelope_sha256=scope.authority_envelope_sha256,
            now=NOW,
        )
