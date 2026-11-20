"""Stage E forwards the same signed request across both root gates."""
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from implementation.kernel import signed_owner_release as signer
from tools import pmv4_e_exact_owner_offer as offer
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_native_root_entry as entry
from tools import pmv4_e_root_bootstrap_once as bootstrap_entry
from tools.tests.test_pmv4_e_signed_bootstrap_phase import fixtures
from tools.tests.test_pmv4_e_signed_native_ledger import CANDIDATE, ROLLBACK, KEY, OID


def signed_request():
    draft = contract.draft(candidate_sha=CANDIDATE, rollback_sha=ROLLBACK)
    plan = {
        "candidate": CANDIDATE, "rollback": ROLLBACK,
        "scope_sha256": draft["scope_sha256"],
        "manifest_sha256": draft["manifest_sha256"],
        "freeze_sha256": draft["manifest"]["freeze_sha256"],
    }
    return draft, offer.signed_request(
        plan, signer=signer, private=KEY, owner_oid=OID,
    )


def test_forwarded_request_passes_both_original_boundaries(tmp_path):
    draft, request = signed_request()
    forwarded = packet.read_owner_request_stream(BytesIO(packet.canonical(request)))
    root_gate, _, state, journal, _ = fixtures(tmp_path)
    evidence = root_gate.validate(forwarded, at=datetime.now(timezone.utc))
    assert evidence["status"] == "owner_signed_inert_bootstrap_preflight_only"
    proof = entry.require_exact_owner_request(forwarded, draft["manifest"])
    assert proof == request["signed_owner_proof"]
    signer.verify_exact_owner_release(
        proof, public_key=KEY.public_key(),
        expected_candidate_sha=CANDIDATE, expected_rollback_sha=ROLLBACK,
        expected_release_id="release-" + CANDIDATE[:16],
        expected_scope_sha256=draft["scope_sha256"],
        expected_manifest_sha256=draft["manifest_sha256"],
        expected_freeze_sha256=draft["manifest"]["freeze_sha256"],
        at=datetime.now(timezone.utc),
    )
    assert list(journal.iterdir()) == []
    state["ci"] = False
    with pytest.raises(PermissionError, match="PROTECTED_SOURCE_CI_NOT_VERIFIED"):
        root_gate.validate(forwarded, at=datetime.now(timezone.utc))


@pytest.mark.parametrize("change", [
    "candidate", "rollback", "scope", "manifest", "freeze", "action",
    "request_id", "extra", "wrong_proof_type",
])
def test_modified_request_cannot_pass_both_gates(tmp_path, change):
    draft, request = signed_request()
    if change == "candidate": request["candidate_sha"] = "f" * 40
    if change == "rollback": request["rollback_sha"] = "f" * 40
    if change == "scope": request["scope_sha256"] = "f" * 64
    if change == "manifest": request["manifest_sha256"] = "f" * 64
    if change == "freeze": request["freeze_sha256"] = "f" * 64
    if change == "action": request["action"] = "host_reconcile"
    if change == "request_id": request["request_id"] = "release-" + "f" * 16
    if change == "extra": request["extra"] = True
    if change == "wrong_proof_type": request["signed_owner_proof"] = "fake"
    with pytest.raises(PermissionError):
        decoded = packet.read_owner_request_stream(BytesIO(packet.canonical(request)))
        entry.require_exact_owner_request(decoded, draft["manifest"])


def test_bad_signature_denied_by_original_root_gate(tmp_path):
    _, request = signed_request()
    request["signed_owner_proof"]["signature_base64url"] = "A" * 86
    decoded = packet.read_owner_request_stream(BytesIO(packet.canonical(request)))
    root_gate, _, _, journal, _ = fixtures(tmp_path)
    with pytest.raises(PermissionError, match="SIGNATURE_INVALID"):
        root_gate.validate(decoded, at=datetime.now(timezone.utc))
    assert list(journal.iterdir()) == []


@pytest.mark.parametrize("raw", [
    b"", b"{" , b"x" * 32769,
    b'{"schema_version":"1.0","schema_version":"1.0"}',
])
def test_malformed_duplicate_or_oversized_stream_fails_closed(raw):
    with pytest.raises(PermissionError):
        packet.read_owner_request_stream(BytesIO(raw))


def test_text_stream_is_not_accepted():
    with pytest.raises(PermissionError):
        packet.read_owner_request_stream(StringIO("{}"))


def test_forwarded_request_never_substitutes_a_different_candidate(tmp_path, monkeypatch):
    candidate = "a" * 40
    folder = tmp_path / ("pmv4-e-source-only-" + candidate)
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    for name in ("manifest.json", "source-scope.json"):
        path = folder / name
        path.write_text(json.dumps({"candidate_sha": candidate}))
        path.chmod(0o400)
    monkeypatch.setattr(bootstrap_entry, "ARTIFACTS", tmp_path)
    real_lstat = Path.lstat
    def fixture_lstat(path):
        meta = real_lstat(path)
        if path == folder or path.parent == folder:
            return SimpleNamespace(
                st_mode=meta.st_mode, st_uid=1000, st_gid=1000,
                st_nlink=meta.st_nlink, st_size=meta.st_size,
            )
        return meta
    monkeypatch.setattr(Path, "lstat", fixture_lstat)
    supplied = {"candidate_sha": candidate, "signed_owner_proof": {}}
    readback = bootstrap_entry.read_offer(candidate, packet, owner_request=supplied)
    assert readback["owner-proof.json"] is supplied
    with pytest.raises(PermissionError, match="FORWARDED_OWNER_REQUEST_CANDIDATE_MISMATCH"):
        bootstrap_entry.read_offer(candidate, packet, owner_request={
            "candidate_sha": "b" * 40,
        })


@pytest.mark.parametrize("mode", ["--preflight", "--recover-interrupted"])
def test_forwarded_request_is_not_used_for_other_native_modes(mode):
    with pytest.raises(PermissionError, match="FORWARDED_REQUEST_ONLY_VALID_FOR_PROMOTION"):
        entry.main(["--candidate-sha", CANDIDATE, mode, "--owner-request-stdin"])


def test_native_promotion_forwards_same_signed_request_without_new_approval():
    _, request = signed_request()
    seen = []
    receipt = {
        "status": "native_stage_e_six_unit_accepted",
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "approval_id": request["signed_owner_proof"]["payload"]["approval_id"],
        "protected_services_changed": False,
    }
    def runner(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(receipt))
    result = bootstrap_entry.native_promotion(
        CANDIDATE, packet=packet, request=request, forwarded=True, runner=runner,
    )
    assert result == receipt
    assert "--owner-request-stdin" in seen[0][0]
    assert json.loads(seen[0][1]["input"]) == request
    assert seen[0][1]["env"] == {"PATH": "/usr/bin:/bin"}

    seen.clear()
    bootstrap_entry.native_promotion(
        CANDIDATE, packet=packet, request=request, forwarded=False, runner=runner,
    )
    assert "--owner-request-stdin" not in seen[0][0]
    assert seen[0][1]["input"] is None


@pytest.mark.parametrize("field,bad", [
    ("candidate_sha", "f" * 40), ("rollback_sha", "f" * 40),
    ("approval_id", "owner-mcp-" + "f" * 32),
    ("protected_services_changed", True),
    ("status", "not_accepted"),
])
def test_native_receipt_must_match_forwarded_approval(field, bad):
    _, request = signed_request()
    receipt = {
        "status": "native_stage_e_six_unit_accepted",
        "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
        "approval_id": request["signed_owner_proof"]["payload"]["approval_id"],
        "protected_services_changed": False,
    }
    receipt[field] = bad
    with pytest.raises(PermissionError, match="ORIGINAL_NATIVE_ACCEPTANCE_NOT_VERIFIED"):
        bootstrap_entry.native_promotion(
            CANDIDATE, packet=packet, request=request, forwarded=True,
            runner=lambda *args, **kw: SimpleNamespace(
                returncode=0, stdout=json.dumps(receipt)),
        )
