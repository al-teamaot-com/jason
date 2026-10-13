from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools" / "offline_release_attestation.py"
spec = importlib.util.spec_from_file_location("offline_release_attestation_test", MODULE)
verify = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(verify)

NOW = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
BASE = "a" * 40
CANDIDATE = "b" * 40
MAIN = "c" * 40
CHECKS = ("runtime-service", "governed-security-regressions")
ISSUER = "aot-ci-protected"


def _private_and_trust():
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, {ISSUER: key}


def _payload():
    return {
        "schema_version": "1.0",
        "issuer": ISSUER,
        "repository": "al-teamaot-com/jason",
        "source_authority": "aot-approved-secondary",
        "candidate_sha": CANDIDATE,
        "protected_main_sha": MAIN,
        "rollback_sha": BASE,
        "bundle_sha256": "d" * 64,
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "checks": [
            {"name": name, "status": "completed",
             "conclusion": "success", "run_id": str(i + 10)}
            for i, name in enumerate(CHECKS)
        ],
    }


def _envelope(private, payload):
    return {
        "schema_version": "1.0",
        "signer_id": ISSUER,
        "payload": payload,
        "signature_b64": base64.b64encode(private.sign(verify.canonical_bytes(payload))).decode(),
    }


def _evaluate(envelope, trusted_signers, *, now=NOW):
    return verify.verify_signed_evidence(
        envelope, trusted_signers=trusted_signers,
        expected_candidate_sha=CANDIDATE, expected_rollback_sha=BASE,
        expected_repository="al-teamaot-com/jason", required_checks=CHECKS,
        now=now,
    )


def test_signed_complete_fresh_ci_evidence_accepted():
    private, trusted = _private_and_trust()
    result = _evaluate(_envelope(private, _payload()), trusted)
    assert result["candidate_sha"] == CANDIDATE
    assert result["bundle_sha256"] == "d" * 64
    assert result["signer_id"] == ISSUER


@pytest.mark.parametrize("tamper", [
    lambda p: p.update(candidate_sha="e" * 40),
    lambda p: p.update(bundle_sha256="f" * 64),
    lambda p: p.update(repository="other-company/other-repo"),
    lambda p: p["checks"].pop(),
    lambda p: p["checks"][0].update(conclusion="failure"),
])
def test_post_signature_tampering_rejected(tamper):
    private, trusted = _private_and_trust()
    payload = _payload()
    envelope = _envelope(private, payload)
    tamper(payload)
    with pytest.raises(verify.OfflineAttestationError, match="signature"):
        _evaluate(envelope, trusted)


def test_unsigned_or_unknown_signer_is_rejected():
    private, trusted = _private_and_trust()
    envelope = _envelope(private, _payload())
    with pytest.raises(verify.OfflineAttestationError, match="trusted CI keyring"):
        _evaluate(envelope, {})
    del envelope["signature_b64"]
    with pytest.raises(verify.OfflineAttestationError, match="schema"):
        _evaluate(envelope, trusted)


@pytest.mark.parametrize("change", [
    lambda p: p.update(source_authority="github"),
    lambda p: p.update(repository="another/repo"),
    lambda p: p.update(candidate_sha="d" * 40),
    lambda p: p.update(rollback_sha="d" * 40),
    lambda p: p.update(issuer="not-the-signer"),
    lambda p: p["checks"][0].update(conclusion="cancelled"),
    lambda p: p["checks"][0].update(status="in_progress"),
    lambda p: p["checks"][0].update(name="different-check"),
    lambda p: p["checks"][0].update(run_id=""),
    lambda p: p["checks"][1].update(name=p["checks"][0]["name"]),
])
def test_signed_but_inadequate_evidence_is_rejected(change):
    private, trusted = _private_and_trust()
    payload = _payload()
    change(payload)
    with pytest.raises(verify.OfflineAttestationError):
        _evaluate(_envelope(private, payload), trusted)


def test_expired_or_future_dated_or_undated_evidence_rejected():
    private, trusted = _private_and_trust()
    envelope = _envelope(private, _payload())
    with pytest.raises(verify.OfflineAttestationError):
        _evaluate(envelope, trusted, now=NOW + timedelta(days=1))
    with pytest.raises(verify.OfflineAttestationError):
        _evaluate(envelope, trusted, now=NOW - timedelta(days=1))
    payload = _payload()
    payload["generated_at"] = "2026-10-13T14:00:00"
    with pytest.raises(verify.OfflineAttestationError):
        _evaluate(_envelope(private, payload), trusted)


def test_unexpected_fields_even_when_signed_rejected():
    private, trusted = _private_and_trust()
    payload = _payload()
    payload["approval"] = True
    with pytest.raises(verify.OfflineAttestationError, match="schema"):
        _evaluate(_envelope(private, payload), trusted)


def _run(*argv, cwd=None):
    return subprocess.check_output(argv, text=True, cwd=cwd).strip()


def _bundle_fixture(tmp_path):
    repo = tmp_path / "src"
    repo.mkdir()
    _run("git", "init", "-q", str(repo))
    _run("git", "config", "user.email", "tests@example.invalid", cwd=repo)
    _run("git", "config", "user.name", "Tests", cwd=repo)
    commits = []
    for value in ("base", "candidate", "protected-main"):
        (repo / "source.txt").write_text(value)
        _run("git", "add", "source.txt", cwd=repo)
        _run("git", "commit", "-qm", value, cwd=repo)
        commits.append(_run("git", "rev-parse", "HEAD", cwd=repo))
    bundle = tmp_path / "candidate.bundle"
    _run("git", "bundle", "create", str(bundle), "HEAD", cwd=repo)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    return bundle, digest, commits


def test_complete_source_bundle_and_exact_ancestry_import(tmp_path):
    bundle, digest, (base, candidate, protected_main) = _bundle_fixture(tmp_path)
    verify.verify_source_bundle(
        bundle, expected_bundle_sha256=digest,
        candidate_sha=candidate, protected_main_sha=protected_main,
        rollback_sha=base,
    )


def test_bundle_digest_mismatch_fails_without_git_import(tmp_path):
    bundle, digest, (base, candidate, protected_main) = _bundle_fixture(tmp_path)
    with pytest.raises(verify.OfflineAttestationError, match="digest"):
        verify.verify_source_bundle(
            bundle, expected_bundle_sha256="0" * 64,
            candidate_sha=candidate, protected_main_sha=protected_main,
            rollback_sha=base,
        )


def test_bundle_rejects_candidate_not_on_signed_protected_main(tmp_path):
    bundle, digest, (base, candidate, protected_main) = _bundle_fixture(tmp_path)
    with pytest.raises(verify.OfflineAttestationError, match="ancestry"):
        verify.verify_source_bundle(
            bundle, expected_bundle_sha256=digest,
            candidate_sha=protected_main, protected_main_sha=candidate,
            rollback_sha=base,
        )


def test_bundle_rejects_missing_commit(tmp_path):
    bundle, digest, (base, candidate, protected_main) = _bundle_fixture(tmp_path)
    with pytest.raises(verify.OfflineAttestationError, match="ancestry"):
        verify.verify_source_bundle(
            bundle, expected_bundle_sha256=digest,
            candidate_sha="f" * 40, protected_main_sha=protected_main,
            rollback_sha=base,
        )


def test_bundle_rejects_symlink(tmp_path):
    bundle, digest, (base, candidate, protected_main) = _bundle_fixture(tmp_path)
    link = tmp_path / "link.bundle"
    link.symlink_to(bundle)
    with pytest.raises(verify.OfflineAttestationError, match="symlinked"):
        verify.verify_source_bundle(
            link, expected_bundle_sha256=digest,
            candidate_sha=candidate, protected_main_sha=protected_main,
            rollback_sha=base,
        )


def test_complete_signed_source_attestation_succeeds_without_granting_deployment(tmp_path):
    bundle, digest, (base, candidate, main) = _bundle_fixture(tmp_path)
    private, trusted = _private_and_trust()
    payload = _payload()
    payload.update(
        candidate_sha=candidate, rollback_sha=base,
        protected_main_sha=main, bundle_sha256=digest,
    )
    result = verify.verify_offline_release_candidate(
        envelope=_envelope(private, payload), bundle=bundle,
        trusted_signers=trusted, expected_candidate_sha=candidate,
        expected_rollback_sha=base, expected_repository="al-teamaot-com/jason",
        required_checks=CHECKS, now=NOW,
    )
    assert result["source_integrity"] == "verified"
    assert result["signed_ci_evidence"] == "verified"
    assert result["production_approval"] is False
    assert result["production_deployed"] is False


def test_combined_preflight_rejects_unsigned_real_source_even_if_hash_correct(tmp_path):
    bundle, digest, (base, candidate, main) = _bundle_fixture(tmp_path)
    private, _trusted = _private_and_trust()
    payload = _payload()
    payload.update(
        candidate_sha=candidate, rollback_sha=base,
        protected_main_sha=main, bundle_sha256=digest,
    )
    with pytest.raises(verify.OfflineAttestationError, match="trusted CI keyring"):
        verify.verify_offline_release_candidate(
            envelope=_envelope(private, payload), bundle=bundle,
            trusted_signers={}, expected_candidate_sha=candidate,
            expected_rollback_sha=base, expected_repository="al-teamaot-com/jason",
            required_checks=CHECKS, now=NOW,
        )
