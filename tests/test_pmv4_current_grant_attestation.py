"""Fresh signer-attested status after ONE authenticated Owner objective consent."""
from __future__ import annotations

from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from kernel.signed_owner_release import canonical
from tools.pmv4_current_grant_attestation import (
    PlanGrantAttestationDenied,
    issue_current_grant_attestation,
    verify_current_grant_attestation,
)
from test_pmv4_owner_objective_end_to_end import (
    AT, enrolled, enroll,
)


@pytest.fixture
def attested(enrolled):
    env = enrolled
    parent = enroll(env)
    key = env["owner_key"]
    signed = issue_current_grant_attestation(
        objective=env["objective"], signed_parent=parent, ledger=env["ledger"],
        signer_private_key=key, pinned_public_key=key.public_key(),
        action_index=3, at=AT,
    )
    return env, parent, signed


def verify(attested, **kwargs):
    env, parent, attestation = attested
    return verify_current_grant_attestation(
        objective=env["objective"], signed_parent=parent,
        signed_attestation=attestation,
        pinned_public_key=env["owner_key"].public_key(),
        expected_action_index=3, at=AT + timedelta(seconds=1), **kwargs,
    )


def test_current_unrevoked_grant_signed_once_without_second_owner_decision(attested):
    env, parent, signed = attested
    result = verify(attested)
    assert result["status"] == "cryptographically_verified_current_plan_no_root_authority"
    assert result["parent_approval_id"] == parent["payload"]["parent_approval_id"]
    assert result["step_index"] == 3
    assert result["no_root_mutation"] is True
    assert len(env["consents"]) == 1
    second = issue_current_grant_attestation(
        objective=env["objective"], signed_parent=parent, ledger=env["ledger"],
        signer_private_key=env["owner_key"],
        pinned_public_key=env["owner_key"].public_key(),
        action_index=3, at=AT + timedelta(seconds=2),
    )
    assert second["payload"]["observed_at"] != signed["payload"]["observed_at"]
    assert len(env["consents"]) == 1


def test_attestation_expires_even_while_parent_objective_is_valid(attested):
    env, parent, attestation = attested
    with pytest.raises(PlanGrantAttestationDenied, match="STALE_OR_EXPIRED"):
        verify_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            signed_attestation=attestation,
            pinned_public_key=env["owner_key"].public_key(),
            expected_action_index=3, at=AT + timedelta(seconds=30),
        )


def test_grant_revocation_denies_new_signed_assertion(attested):
    env, parent, attestation = attested
    env["ledger"].revoke(
        env["objective"].plan_id, at=AT + timedelta(seconds=1),
        reason="Owner canceled objective",
    )
    with pytest.raises(PermissionError):
        issue_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            ledger=env["ledger"], signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=3, at=AT + timedelta(seconds=2),
        )


@pytest.mark.parametrize("fault", [
    "unsigned", "wrong_signature", "scope", "plan_id", "owner",
    "action", "rollback", "grant_false", "parent_hash", "future",
    "long_ttl", "standing_authority", "foreign_field",
])
def test_signature_and_freshness_alone_cannot_expand_exact_action(attested, fault):
    env, parent, signed = attested
    signed = {"payload": dict(signed["payload"]),
              "signature_base64url": signed["signature_base64url"]}
    item = signed["payload"]
    if fault == "unsigned":
        signed = {"payload": item, "signature_base64url": "not-signed"}
    elif fault == "wrong_signature":
        signed["signature_base64url"] = "A" * 86
    elif fault == "scope":
        item["scope_sha256"] = "1" * 64
    elif fault == "plan_id":
        item["parent_plan_id"] = "other-plan"
    elif fault == "owner":
        item["owner_oid"] = "unknown-owner"
    elif fault == "action":
        item["action"] = "root.shell.unbounded"
    elif fault == "rollback":
        item["rollback_sha"] = "a" * 40
    elif fault == "grant_false":
        item["current_grant_status"] = "unverified"
    elif fault == "parent_hash":
        item["parent_signed_sha256"] = "a" * 64
    elif fault == "future":
        item["observed_at"] = (AT + timedelta(minutes=3)).isoformat()
    elif fault == "long_ttl":
        item["expires_at"] = (AT + timedelta(hours=1)).isoformat()
    elif fault == "standing_authority":
        item["standing_authority"] = True
    elif fault == "foreign_field":
        item["shell"] = "sh -c bypass"
    if fault not in {"unsigned", "wrong_signature"}:
        key = env["owner_key"]
        import base64
        signed["signature_base64url"] = base64.urlsafe_b64encode(
            key.sign(canonical(item))
        ).decode("ascii").rstrip("=")
    with pytest.raises(PlanGrantAttestationDenied):
        verify_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            signed_attestation=signed,
            pinned_public_key=env["owner_key"].public_key(),
            expected_action_index=3, at=AT + timedelta(seconds=1),
        )


def test_foreign_pinned_public_key_cannot_validate_root_status(attested):
    env, parent, signed = attested
    foreign = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(PlanGrantAttestationDenied):
        verify_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            signed_attestation=signed, pinned_public_key=foreign,
            expected_action_index=3, at=AT,
        )


def test_changed_original_parent_signature_blocks_attestation(attested):
    env, parent, signed = attested
    changed = {**parent, "signature_base64url": "A" * 86}
    with pytest.raises(PlanGrantAttestationDenied):
        verify_current_grant_attestation(
            objective=env["objective"], signed_parent=changed,
            signed_attestation=signed,
            pinned_public_key=env["owner_key"].public_key(),
            expected_action_index=3, at=AT,
        )


def test_issuer_must_be_trusted_match_pinned_signer(attested):
    env, parent, signed = attested
    with pytest.raises(PlanGrantAttestationDenied, match="ATTESTOR_TRUST_REQUIRED"):
        issue_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            ledger=env["ledger"],
            signer_private_key=Ed25519PrivateKey.generate(),
            pinned_public_key=env["owner_key"].public_key(),
            action_index=3, at=AT,
        )


def test_root_production_policy_is_still_off(attested):
    env, parent, signed = attested
    with pytest.raises(PlanGrantAttestationDenied, match="ROOT_ATTESTOR_NOT_DEPLOYED"):
        issue_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            ledger=env["ledger"], signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=3, at=AT, production=True,
        )
    with pytest.raises(PlanGrantAttestationDenied, match="ROOT_CONSUMER_NOT_DEPLOYED"):
        verify_current_grant_attestation(
            objective=env["objective"], signed_parent=parent,
            signed_attestation=signed,
            pinned_public_key=env["owner_key"].public_key(),
            expected_action_index=3, at=AT, production=True,
        )
