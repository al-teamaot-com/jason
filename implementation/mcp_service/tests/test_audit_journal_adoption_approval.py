"""Exact licensed Owner ChatGPT signature, one-use and scope denial tests."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from jason_mcp.audit_journal_adoption_approval import (
    ACTION, APPROVAL_WORDS, ARCHIVE, ROLLBACK, LICENSED_OWNER,
    AuditJournalApprovalDenied, canonical, queue_exact_archive_owner_approval,
    validate_offer,
)
from kernel.signed_owner_release import (
    verify_exact_owner_release, OwnerReleaseProofDenied,
)
OWNER = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
CLAIMS = {"tid": "f7054323-d52b-4863-8c2f-1898f0b6077c",
          "oid": LICENSED_OWNER}
CANDIDATE = "a" * 40


def offer_data():
    return {
        "schema_version": "1.0", "action": ACTION,
        "release_id": "release-" + CANDIDATE[:16],
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "scope_sha256": "b" * 64, "manifest_sha256": "c" * 64,
        "freeze_sha256": "d" * 64, "archive_root": ARCHIVE,
        "owner_oid": LICENSED_OWNER, "production_breaker_verified": True,
        "production_drift_verified": True, "protected_peers_verified": True,
        "separate_archive_mount_verified": True, "journal_only": True,
        "availability_interruption_authorized": True,
        "one_use": True, "standing_authority": False,
        "production_mutations": False,
        "root_stage_receipt_sha256": "e" * 64,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }


def prepared(tmp_path: Path):
    for part in ("offers", "owner-approvals"):
        p = tmp_path / part
        p.mkdir(mode=0o700)
        p.chmod(0o700)
    offer = offer_data()
    p = tmp_path / "offers" / (offer["release_id"] + ".json")
    p.write_bytes(canonical(offer))
    p.chmod(0o600)
    return offer


def sign(tmp_path, offer, signer, **overrides):
    kwargs = {
        "state_root": tmp_path, "release_id": offer["release_id"],
        "candidate_sha": offer["candidate_sha"],
        "scope_sha256": offer["scope_sha256"],
        "manifest_sha256": offer["manifest_sha256"],
        "approved_by": OWNER, "organization_id": "aot",
        "verified_token_claims": CLAIMS,
        "service_signer": signer,
        "affirmative_decision": APPROVAL_WORDS,
    }
    kwargs.update(overrides)
    return queue_exact_archive_owner_approval(**kwargs)


def test_exact_root_staged_owner_chatgpt_signature_not_production(tmp_path):
    offer = prepared(tmp_path)
    signer = Ed25519PrivateKey.generate()
    receipt = sign(tmp_path, offer, signer)
    assert receipt["status"] == "signed_exact_owner_approval_queued_not_deployed"
    assert receipt["production_mutations"] is False
    assert receipt["owner_approval_is_one_use"] is True
    root = json.loads((tmp_path / "owner-approvals" /
                       (offer["release_id"] + ".json")).read_bytes())
    assert root["action"] == ACTION
    assert root["production_mutations"] is False
    assert root["root_stage_receipt_sha256"] == offer["root_stage_receipt_sha256"]
    payload = verify_exact_owner_release(
        root["signed_owner_proof"], public_key=signer.public_key(),
        expected_candidate_sha=CANDIDATE, expected_rollback_sha=ROLLBACK,
        expected_release_id=offer["release_id"],
        expected_scope_sha256=offer["scope_sha256"],
        expected_manifest_sha256=offer["manifest_sha256"],
        expected_freeze_sha256=offer["freeze_sha256"],
        at=datetime.now(timezone.utc),
    )
    assert payload["owner_oid"] == LICENSED_OWNER
    assert payload["one_release_only"] is True
    assert payload["standing_authority"] is False
    with pytest.raises(AuditJournalApprovalDenied, match="ONE_USE_APPROVAL_REPLAY"):
        sign(tmp_path, offer, signer)


@pytest.mark.parametrize("overrides", [
    {"affirmative_decision": ""},
    {"affirmative_decision": "approve"},
    {"approved_by": "person-other"},
    {"organization_id": "client"},
    {"verified_token_claims": {"tid": "other", "oid": LICENSED_OWNER}},
    {"verified_token_claims": {"tid": CLAIMS["tid"], "oid": "0" * 36}},
    {"service_signer": None},
    {"candidate_sha": "f" * 40},
    {"scope_sha256": "0" * 64},
    {"manifest_sha256": "0" * 64},
    {"release_id": "release-" + "f" * 16},
])
def test_wrong_actor_token_or_scope_refused_before_signature(tmp_path, overrides):
    offer = prepared(tmp_path)
    signer = Ed25519PrivateKey.generate()
    with pytest.raises(AuditJournalApprovalDenied):
        sign(tmp_path, offer, signer, **overrides)
    assert list((tmp_path / "owner-approvals").iterdir()) == []


@pytest.mark.parametrize("mutation", [
    lambda row: row.update(action="full_release"),
    lambda row: row.update(rollback_sha="f" * 40),
    lambda row: row.update(archive_root="/tmp"),
    lambda row: row.update(production_breaker_verified=False),
    lambda row: row.update(production_drift_verified=False),
    lambda row: row.update(protected_peers_verified=False),
    lambda row: row.update(separate_archive_mount_verified=False),
    lambda row: row.update(journal_only=False),
    lambda row: row.update(availability_interruption_authorized=False),
    lambda row: row.update(one_use=False),
    lambda row: row.update(standing_authority=True),
    lambda row: row.update(production_mutations=True),
    lambda row: row.update(owner_oid="unknown"),
    lambda row: row.update(candidate_sha="0" * 40),
    lambda row: row.update(scope_sha256="invalid"),
    lambda row: row.update(prepared_at=(
        datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()),
    lambda row: row.update(prepared_at=(
        datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()),
    lambda row: row.update(foreign_field=True),
])
def test_wrong_or_stale_root_offer_never_signs(tmp_path, mutation):
    offer = prepared(tmp_path)
    content = dict(offer)
    mutation(content)
    p = tmp_path / "offers" / (offer["release_id"] + ".json")
    p.write_bytes(canonical(content))
    with pytest.raises(AuditJournalApprovalDenied):
        sign(tmp_path, offer, Ed25519PrivateKey.generate())
    assert list((tmp_path / "owner-approvals").iterdir()) == []


def test_symlinked_offer_denied(tmp_path):
    offer = prepared(tmp_path)
    source = tmp_path / "offers" / (offer["release_id"] + ".json")
    target = tmp_path / "untrusted.json"
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises(AuditJournalApprovalDenied):
        sign(tmp_path, offer, Ed25519PrivateKey.generate())


def test_public_receipt_wrong_signature_and_replay_denied(tmp_path):
    offer = prepared(tmp_path)
    signer = Ed25519PrivateKey.generate()
    sign(tmp_path, offer, signer)
    row = json.loads((tmp_path / "owner-approvals" /
                      (offer["release_id"] + ".json")).read_bytes())
    with pytest.raises(OwnerReleaseProofDenied):
        verify_exact_owner_release(
            row["signed_owner_proof"], public_key=Ed25519PrivateKey.generate().public_key(),
            expected_candidate_sha=CANDIDATE, expected_rollback_sha=ROLLBACK,
            expected_release_id=offer["release_id"],
            expected_scope_sha256=offer["scope_sha256"],
            expected_manifest_sha256=offer["manifest_sha256"],
            expected_freeze_sha256=offer["freeze_sha256"],
            at=datetime.now(timezone.utc))


def test_no_root_offer_or_approval_directory_is_not_created(tmp_path):
    with pytest.raises(AuditJournalApprovalDenied):
        sign(tmp_path, offer_data(), Ed25519PrivateKey.generate())
    assert not (tmp_path / "owner-approvals").exists()
    assert not (tmp_path / "offers").exists()


def test_server_exposes_disabled_by_default_exact_archive_tool_without_root_action():
    import ast
    root=Path(__file__).resolve().parents[1]
    content=(root/"src/jason_mcp/server.py").read_text()
    tree=ast.parse(content)
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name=="approve_audit_journal_adoption"]
    assert len(functions)==1
    node=functions[0]
    assert len(node.decorator_list)==1
    assert isinstance(node.decorator_list[0],ast.Call)
    assert isinstance(node.decorator_list[0].func,ast.Attribute)
    assert node.decorator_list[0].func.attr=="tool"
    source=ast.get_source_segment(content,node)
    assert 'JASON_AUDIT_JOURNAL_OWNER_ISSUER_ENABLED' in source
    assert 'AUDIT_JOURNAL_OWNER_ISSUER_NOT_ACTIVATED' in source
    assert '_release_approval_owner()' in source
    assert 'get_access_token()' in source
    assert 'queue_exact_archive_owner_approval' in source
    assert 'affirmative_decision=affirmative_decision' in source
    assert 'systemctl' not in source and 'subprocess' not in source
    assert 'os.system' not in source and 'sudo' not in source
