"""Offline Stage E MCP approval compatibility and denial checks."""
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel import signed_owner_release as signer
from jason_mcp import pmv4_e_owner_bridge as bridge
from tools import pmv4_e_signed_bootstrap_phase as bootstrap


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
CANDIDATE = "a" * 40
ROLLBACK = "b" * 40
SCOPE = "c" * 64
MANIFEST = "d" * 64
FREEZE = "e" * 64


@pytest.fixture
def args():
    now = int(NOW.timestamp())
    claims = {
        "tid": signer.TID, "oid": signer.OWNER_OID, "iss": bridge.ISSUER,
        "aud": bridge.APP_ID, "iat": now - 15, "nbf": now - 15,
        "exp": now + 180,
    }
    return {
        "bearer_token": "synthetic-verified-entra-token",
        "verified_principal": signer.OWNER_PRINCIPAL,
        "verified_organization": "aot",
        "verify_entra_bearer": lambda _: dict(claims),
        "exact_owner_consent": lambda _: True,
        "source_review": lambda candidate, rollback: (
            candidate == CANDIDATE and rollback == ROLLBACK
        ),
        "reviewed_offer": {
            "candidate": CANDIDATE, "rollback": ROLLBACK,
            "scope_sha256": SCOPE, "manifest_sha256": MANIFEST,
            "freeze_sha256": FREEZE,
        },
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "scope_sha256": SCOPE, "manifest_sha256": MANIFEST,
        "freeze_sha256": FREEZE,
        "affirmative_decision": "approve_exact_pmv4_stage_e_cutover",
        "signing_key": Ed25519PrivateKey.generate(), "at": NOW,
        "production": False,
    }


def test_authenticated_exact_decision_produces_native_compatible_signature(args):
    seen = []
    args["exact_owner_consent"] = lambda binding: seen.append(binding) or True
    result = bridge.build_stage_e_request(**args)
    request = result["request"]
    assert set(request) == bootstrap.FIELDS
    assert request["action"] == bootstrap.BOOTSTRAP_ACTION
    assert result["production_authorized"] is False
    assert result["production_mutations"] is False
    assert seen == [{
        "service": "pmv4-stage-e-six-unit-cutover",
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "scope_sha256": SCOPE, "manifest_sha256": MANIFEST,
        "freeze_sha256": FREEZE, "owner_principal": signer.OWNER_PRINCIPAL,
    }]
    proof = request["signed_owner_proof"]
    verified = signer.verify_exact_owner_release(
        proof, public_key=args["signing_key"].public_key(),
        expected_candidate_sha=CANDIDATE, expected_rollback_sha=ROLLBACK,
        expected_release_id="release-" + CANDIDATE[:16],
        expected_scope_sha256=SCOPE, expected_manifest_sha256=MANIFEST,
        expected_freeze_sha256=FREEZE, at=NOW,
    )
    assert verified["owner_principal"] == signer.OWNER_PRINCIPAL
    assert verified["one_release_only"] is True
    with pytest.raises(signer.OwnerReleaseProofDenied):
        signer.verify_exact_owner_release(
            proof, public_key=args["signing_key"].public_key(),
            expected_candidate_sha=CANDIDATE, expected_rollback_sha=ROLLBACK,
            expected_release_id="release-" + CANDIDATE[:16],
            expected_scope_sha256=SCOPE, expected_manifest_sha256=MANIFEST,
            expected_freeze_sha256=FREEZE, at=NOW + timedelta(minutes=16),
        )


@pytest.mark.parametrize("field, value", [
    ("candidate_sha", "f" * 40), ("rollback_sha", "f" * 40),
    ("scope_sha256", "f" * 64), ("manifest_sha256", "f" * 64),
    ("freeze_sha256", "f" * 64),
    ("verified_organization", "other"),
    ("verified_principal", "forged"),
    ("affirmative_decision", "approve"),
    ("bearer_token", ""),
])
def test_changed_scope_or_identity_is_denied(args, field, value):
    args[field] = value
    with pytest.raises(PermissionError):
        bridge.build_stage_e_request(**args)


@pytest.mark.parametrize("field, value", [
    ("tid", "wrong-tenant"), ("oid", "wrong-owner"),
    ("iss", "wrong-issuer"), ("aud", "wrong-audience"),
    ("iat", int(NOW.timestamp()) - 901),
    ("nbf", int(NOW.timestamp()) + 1),
    ("exp", int(NOW.timestamp())),
])
def test_untrusted_or_stale_entra_claims_are_denied(args, field, value):
    original = args["verify_entra_bearer"]
    def changed(token):
        claims = original(token)
        claims[field] = value
        return claims
    args["verify_entra_bearer"] = changed
    with pytest.raises(PermissionError, match="CLAIMS_DENIED"):
        bridge.build_stage_e_request(**args)


def test_denied_consent_and_production_remain_closed(args):
    args["exact_owner_consent"] = lambda _: False
    with pytest.raises(PermissionError, match="EXACT_DECISION_REQUIRED"):
        bridge.build_stage_e_request(**args)
    del args["production"]
    with pytest.raises(PermissionError, match="ROOT_DISPATCH_NOT_DEPLOYED"):
        bridge.build_stage_e_request(**args)


def test_signed_mcp_request_passes_original_inert_root_gate(tmp_path, args):
    from tools import pmv4_e_native_release_contract as contract
    from tools.tests.test_pmv4_e_signed_bootstrap_phase import fixtures
    from tools.tests.test_pmv4_e_signed_native_ledger import (
        CANDIDATE as ROOT_CANDIDATE, ROLLBACK as ROOT_ROLLBACK, KEY,
    )

    root_gate, _, state, journal, _ = fixtures(tmp_path)
    reviewed = contract.draft(candidate_sha=ROOT_CANDIDATE,
                              rollback_sha=ROOT_ROLLBACK)
    args.update({
        "candidate_sha": ROOT_CANDIDATE,
        "rollback_sha": ROOT_ROLLBACK,
        "scope_sha256": reviewed["scope_sha256"],
        "manifest_sha256": reviewed["manifest_sha256"],
        "freeze_sha256": reviewed["manifest"]["freeze_sha256"],
        "signing_key": KEY,
    })
    args["source_review"] = lambda candidate, rollback: (
        candidate == ROOT_CANDIDATE and rollback == ROOT_ROLLBACK
    )
    args["reviewed_offer"] = {
        "candidate": ROOT_CANDIDATE, "rollback": ROOT_ROLLBACK,
        "scope_sha256": reviewed["scope_sha256"],
        "manifest_sha256": reviewed["manifest_sha256"],
        "freeze_sha256": reviewed["manifest"]["freeze_sha256"],
    }
    request = bridge.build_stage_e_request(**args)["request"]
    assert root_gate.validate(request, at=NOW)["status"] == (
        "owner_signed_inert_bootstrap_preflight_only"
    )
    state["ci"] = False
    with pytest.raises(PermissionError, match="PROTECTED_SOURCE_CI_NOT_VERIFIED"):
        root_gate.validate(request, at=NOW)
    assert list(journal.iterdir()) == []


def test_failed_source_review_denies_before_owner_proof(args):
    seen = []
    args["source_review"] = lambda *_: False
    args["exact_owner_consent"] = lambda binding: seen.append(binding) or True
    with pytest.raises(PermissionError, match="SOURCE_REVIEW_DENIED"):
        bridge.build_stage_e_request(**args)
    assert seen == []
