"""Existing MCP Owner -> exact Stage A0 root request handoff, offline only."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    TID, OWNER_OID, OWNER_PRINCIPAL, verify_exact_owner_release,
)
from jason_mcp import pmv4_stage_a0_owner_issuer as issuer

T = datetime(2026, 11, 12, 11, 0, tzinfo=timezone.utc)
SHA = "d" * 40
SCOPE = "a" * 64
MANIFEST = "b" * 64
EXPECTED = "c" * 64


@pytest.fixture
def call(tmp_path):
    requests = tmp_path / "host-reconcile" / "requests"
    requests.mkdir(parents=True)
    requests.chmod(0o750)
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"synthetic-root-freeze-for-owner-authorization")
    freeze.chmod(0o600)
    signer = tmp_path / "ed25519.private"
    key = Ed25519PrivateKey.generate()
    signer.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    signer.chmod(0o400)
    now = int(T.timestamp())
    claims = {
        "tid": TID, "iss": issuer.ISSUER, "aud": issuer.APP_ID,
        "oid": OWNER_OID,
        "iat": now - 15, "nbf": now - 15, "exp": now + 180,
    }
    consent = []
    args = {
        "bearer_token": "offline-signed-entra-verifier-token",
        "verified_principal": OWNER_PRINCIPAL,
        "verified_organization": "aot",
        "verify_entra_bearer": lambda _: claims,
        "exact_owner_consent": lambda binding: consent.append(binding) or True,
        "protected_main_check": lambda sha: sha == SHA,
        "candidate_sha": SHA, "reviewed_scope_sha256": SCOPE,
        "manifest_sha256": MANIFEST,
        "freeze_sha256": sha256(freeze.read_bytes()).hexdigest(),
        "affirmative_decision": "approve_exact_pmv4_stage_a0_install",
        "production": False, "requests_path": requests,
        "freeze_path": freeze, "signer_path": signer, "at": T,
    }
    return args, key, consent


def test_one_use_authenticated_owner_emits_bounded_root_request(call):
    args, key, consent = call
    out = issuer.issue_stage_a0_request(**args)
    assert out["status"] == "signed_exact_stage_a0_request_queued"
    assert out["standing_authority"] is False
    assert out["production_installed"] is False
    assert out["production_deployment"] is False
    assert len(consent) == 1
    assert consent[0] == {
        "service": "pmv4-stage-a0-host-bootstrap",
        "candidate_sha": SHA, "rollback_sha": "0"*40,
        "scope_sha256": SCOPE, "manifest_sha256": MANIFEST,
        "freeze_sha256": args["freeze_sha256"],
        "owner_principal": OWNER_PRINCIPAL,
    }
    records = list(args["requests_path"].glob("*.json"))
    assert len(records) == 1 and len(list(args["requests_path"].glob("*.tmp"))) == 0
    row = records[0]
    assert row.stat().st_nlink == 1
    assert row.stat().st_uid == os.geteuid()
    assert row.stat().st_mode & 0o777 == 0o600
    payload = json.loads(row.read_text())
    assert set(payload) == {
        "request_id", "source_revision", "action", "scope_sha256",
        "manifest_sha256", "freeze_sha256", "signed_owner_proof",
    }
    assert payload["action"] == "pmv4_stage_a0_install"
    verified = verify_exact_owner_release(
        payload["signed_owner_proof"], public_key=key.public_key(),
        expected_candidate_sha=SHA,
        expected_rollback_sha="0"*40,
        expected_release_id="release-" + SHA[:16],
        expected_scope_sha256=SCOPE,
        expected_manifest_sha256=MANIFEST,
        expected_freeze_sha256=args["freeze_sha256"],
        at=T,
    )
    assert verified["owner_principal"] == OWNER_PRINCIPAL
    with pytest.raises(issuer.StageA0OwnerIssuerDenied,
                       match="ONE_SOURCE_REQUEST_ALREADY_EXISTS"):
        issuer.issue_stage_a0_request(**args)
    assert row.read_text() == json.dumps(payload, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("change", [
    "wrong_org", "wrong_owner", "missing_confirmation",
    "missing_token", "unprotected_candidate", "scope_short",
    "wrong_freeze", "freeze_missing", "verification_unavailable",
    "issuer_mismatch", "wrong_audience", "wrong_tenant",
    "subject_spoof", "expired_claims", "future_claims", "wrong_decision",
])
def test_untrusted_or_expired_owner_request_never_publishes(call, change):
    args, key, consent = call
    args = dict(args)
    if change == "wrong_org": args["verified_organization"] = "untrusted"
    if change == "wrong_owner": args["verified_principal"] = "forged"
    if change == "missing_confirmation": args["exact_owner_consent"] = lambda _: False
    if change == "missing_token": args["bearer_token"] = ""
    if change == "unprotected_candidate": args["protected_main_check"] = lambda _: False
    if change == "scope_short": args["reviewed_scope_sha256"] = "abc"
    if change == "wrong_freeze": args["freeze_sha256"] = "a"*64
    if change == "freeze_missing": args["freeze_path"].unlink()
    if change == "verification_unavailable": args["verify_entra_bearer"] = lambda _: None
    if change in ("issuer_mismatch", "wrong_audience", "wrong_tenant",
                  "subject_spoof", "expired_claims", "future_claims"):
        t = int(T.timestamp())
        claims = {
            "tid": TID, "iss": issuer.ISSUER, "aud": issuer.APP_ID,
            "oid": OWNER_OID, "iat": t - 15, "nbf": t - 15, "exp": t + 180,
        }
        if change == "issuer_mismatch": claims["iss"] = "https://attacker.invalid/"
        if change == "wrong_audience": claims["aud"] = "forged-audience"
        if change == "wrong_tenant": claims["tid"] = "forged-tenant"
        if change == "subject_spoof": claims["oid"] = "forged-oid"
        if change == "expired_claims": claims["exp"] = t-1
        if change == "future_claims": claims["nbf"] = t+1
        args["verify_entra_bearer"] = lambda _: claims
    if change == "wrong_decision": args["affirmative_decision"] = "yes"
    with pytest.raises((PermissionError, ValueError)):
        issuer.issue_stage_a0_request(**args)
    assert list(args["requests_path"].glob("*.json")) == []


def test_wrong_signer_or_untrusted_request_store_fails_closed(call):
    args, _, _ = call
    args["signer_path"].chmod(0o644)
    with pytest.raises(PermissionError):
        issuer.issue_stage_a0_request(**args)
    assert list(args["requests_path"].glob("*.json")) == []
    args["requests_path"].chmod(0o777)
    with pytest.raises(PermissionError, match="SPOOL_UNTRUSTED"):
        issuer.issue_stage_a0_request(**args)


def test_live_path_and_identity_cannot_be_overridden_by_client(call):
    args, _, _ = call
    args["production"] = True
    with pytest.raises(PermissionError, match="PRODUCTION_PATH_OR_IDENTITY_OVERRIDE"):
        issuer.issue_stage_a0_request(**args)


def test_source_deploy_profile_has_explicit_default_off():
    repo = Path(__file__).resolve().parents[1]
    cfg = json.loads((repo / "config/pmv4-stage-a0-issuer-activation.json").read_text())
    assert cfg == {
        "schema_version": "1.0",
        "service": "pmv4-stage-a0-host-bootstrap", "mode": "off",
    }
    script = (repo / "infrastructure/jason-mcp/production-deploy.sh").read_text()
    assert "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false" in script
    assert "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true" in script
    server = (repo / "implementation/mcp_service/src/jason_mcp/server.py").read_text()
    assert "def authorize_pmv4_stage_a0_install(" in server
    assert 'JASON_PMV4_STAGE_A0_ISSUER_ENABLED") != "true"' in server


def test_one_use_request_publishes_only_after_complete_spool_atomic_rename(
    call, monkeypatch,
):
    args, _key, _consent = call
    original = issuer._rename_noreplace
    observed = []
    def trace_publish(source: Path, destination: Path):
        # DirectoryNotEmpty must see an empty watched directory right up
        # to the final atomic rename, not a temporary file that might
        # prematurely consume the systemd path event.
        assert source.parent == args["requests_path"].parent
        assert destination.parent == args["requests_path"]
        assert list(args["requests_path"].iterdir()) == []
        assert source.is_file()
        assert source.stat().st_nlink == 1
        observed.append((source, destination))
        return original(source, destination)
    monkeypatch.setattr(issuer, "_rename_noreplace", trace_publish)
    issuer.issue_stage_a0_request(**args)
    assert len(observed) == 1
    assert observed[0][1].is_file()
    assert not list(args["requests_path"].parent.glob("*.tmp"))
