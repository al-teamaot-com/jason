"""Offline verification for Stage A0 exact Owner source-only admission."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    TID, OWNER_OID, OWNER_PRINCIPAL, canonical, issue_exact_owner_release,
)
from tools import pmv4_stage_a_admission as admit
from tools import pmv4_stage_a_packet as packet

REPO = Path(__file__).resolve().parents[1]
CANDIDATE = "d"*40
ROLLBACK = "0"*40
TIME = datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def approved(tmp_path, monkeypatch):
    monkeypatch.setattr(packet, "verify_exact_repository_head", lambda *_: None)
    monkeypatch.setattr(admit.packet, "verify_exact_repository_head", lambda *_: None)
    key = Ed25519PrivateKey.generate()
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"root-protected-freeze-for-synthetic-admission")
    digest = sha256(freeze.read_bytes()).hexdigest()
    scope = packet.build_scope(REPO, CANDIDATE)
    manifest = admit.exact_stage_a_manifest(scope, digest)
    signature = issue_exact_owner_release(
        approval_id="owner-mcp-"+"a"*32,
        release_id="release-"+CANDIDATE[:16],
        candidate_sha=CANDIDATE, rollback_sha=ROLLBACK,
        scope_sha256=scope["scope_sha256"],
        manifest_sha256=sha256(canonical(manifest)).hexdigest(),
        freeze_sha256=digest,
        verified_tenant_id=TID, verified_owner_oid=OWNER_OID,
        verified_principal=OWNER_PRINCIPAL,
        verified_organization_id="aot", confirmed_decision="approve",
        at=TIME, private_key=key,
    )
    health = {
        "preflight_evidence_satisfied": True,
        "stage_a_empty_baseline_verified": True,
        "root_only_target_parent_verification_needed": False,
        "breaker_state": "closed",
        "installation_ready": False,
        "production_install_authorized": False,
        "freeze_sha256": digest,
    }
    args = {
        "repo": REPO, "candidate_sha": CANDIDATE, "reviewed_scope": scope,
        "exact_manifest": manifest, "signed_owner_proof": signature,
        "frozen_marker": freeze, "confirmed_root_health": health,
        "protected_main_ci_check": lambda sha: sha==CANDIDATE,
        "test_public_key": key.public_key(), "production": False,
        "at": TIME + timedelta(seconds=30),
    }
    return args


def test_exact_one_use_admission_readonly(approved):
    result = admit.verify_admission(**approved)
    assert result["status"] == "source_only_admission_verified"
    assert result["rollback_sha"] == ROLLBACK
    assert result["production_installed"] is False
    assert result["production_mutation"] is False
    assert result["trusted_root_installer_required"] is True


@pytest.mark.parametrize("change", [
    "wrong_scope", "scope_list_changed", "forged_manifest", "freeze_changed",
    "breaker_open", "root_not_ready", "target_missing_root_attestation",
    "source_not_protected", "wrong_candidate", "expired_proof",
    "replayed_owner_decision", "production_test_key_override",
    "production_trust_override",
])
def test_forged_or_stale_authority_fails_closed(approved, change):
    args=approved.copy()
    if change == "wrong_scope":
        sc=deepcopy(args["reviewed_scope"])
        sc["scope_sha256"] = "f"*64
        args["reviewed_scope"] = sc
    if change == "scope_list_changed":
        sc=deepcopy(args["reviewed_scope"])
        sc["files"].pop()
        args["reviewed_scope"] = sc
    if change == "forged_manifest":
        m=deepcopy(args["exact_manifest"])
        m["rollback_sha"]="e"*40
        args["exact_manifest"]=m
    if change == "freeze_changed":
        args["frozen_marker"].write_bytes(b"mutated-freeze")
    if change == "breaker_open":
        h=deepcopy(args["confirmed_root_health"]);h["breaker_state"]="open"
        args["confirmed_root_health"]=h
    if change == "root_not_ready":
        h=deepcopy(args["confirmed_root_health"]);h["preflight_evidence_satisfied"]=False
        args["confirmed_root_health"]=h
    if change == "target_missing_root_attestation":
        h=deepcopy(args["confirmed_root_health"])
        h["root_only_target_parent_verification_needed"]=True
        args["confirmed_root_health"]=h
    if change == "source_not_protected":
        args["protected_main_ci_check"]=lambda sha: False
    if change == "wrong_candidate":
        args["candidate_sha"]="e"*40
    if change == "expired_proof":
        args["at"]=TIME+timedelta(minutes=16)
    if change == "replayed_owner_decision":
        args["consumed_ids"]=frozenset({"owner-mcp-"+"a"*32})
    if change == "production_test_key_override":
        args["production"]=True
    if change == "production_trust_override":
        args["production"]=True
        args["test_public_key"]=None
        args["pinned_trust"]=Path("/tmp/untrusted-owner-public-key")
    with pytest.raises((admit.StageAAdmissionDenied, ValueError)):
        admit.verify_admission(**args)


def test_missing_signed_proof_fails_closed(approved):
    args=approved.copy()
    args["signed_owner_proof"]={}
    with pytest.raises(admit.StageAAdmissionDenied, match="OWNER_SIGNED_DECISION_INVALID"):
        admit.verify_admission(**args)


def test_manifest_rejects_enabled_issuer_or_mutation(approved):
    for name,value in [
        ("owner_issuer_enabled",True), ("production_services_restart",True),
        ("production_freeze_change",True), ("breaker_mutation",True),
        ("provider_writes",True), ("install_approval_required",False),
    ]:
        scope=deepcopy(approved["reviewed_scope"])
        scope[name]=value
        with pytest.raises(admit.StageAAdmissionDenied, match="SCOPE_IDENTITY_NOT_SAFE"):
            admit.exact_stage_a_manifest(scope,approved["exact_manifest"]["freeze_sha256"])
