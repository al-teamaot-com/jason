"""Stage E authenticated issuer queues a request the root dispatcher understands."""
from pathlib import Path
from types import SimpleNamespace
import json
import os

import pytest

from implementation.kernel.signed_owner_release import verify_exact_owner_release
from jason_mcp import pmv4_e_owner_bridge as issuer
from tools import release_host_reconcile_worker as worker
from tests.test_pmv4_stage_a0_owner_issuer import call, T, SHA, SCOPE, MANIFEST

ROLLBACK = "a" * 40


def stage_e_args(call):
    args, key, consent = call
    args = dict(args)
    args["rollback_sha"] = ROLLBACK
    args["scope_sha256"] = args.pop("reviewed_scope_sha256")
    args["affirmative_decision"] = "approve_exact_pmv4_stage_e_cutover"
    return args, key, consent


def test_issuer_and_root_dispatch_share_same_signed_contract(call, monkeypatch):
    args, key, consent = stage_e_args(call)
    result = issuer.issue_stage_e_request(**args)
    assert result["status"] == "signed_exact_stage_e_request_queued"
    assert result["standing_authority"] is False
    assert result["production_deployment"] is False
    assert len(consent) == 1 and consent[0]["rollback_sha"] == ROLLBACK
    path = args["requests_path"] / (result["request_id"] + ".json")
    account_lookup = SimpleNamespace(
        getpwnam=lambda _: SimpleNamespace(pw_uid=os.getuid()),
    )
    monkeypatch.setattr(worker, "pwd", account_lookup)
    envelope = worker._read_request(path)
    request = envelope["owner_request"]
    assert request["action"] == issuer.BOOTSTRAP_ACTION
    proof = verify_exact_owner_release(
        request["signed_owner_proof"], public_key=key.public_key(),
        expected_candidate_sha=SHA, expected_rollback_sha=ROLLBACK,
        expected_release_id="release-" + SHA[:16],
        expected_scope_sha256=SCOPE, expected_manifest_sha256=MANIFEST,
        expected_freeze_sha256=args["freeze_sha256"], at=T)
    assert proof["approval_id"] == result["approval_id"]
    assert path.stat().st_nlink == 1
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("change", [
    "candidate", "rollback", "scope", "wrong_freeze", "decision", "owner",
    "consent", "main", "claims", "signer", "spool",
])
def test_untrusted_issuer_inputs_never_queue_a_request(call, change):
    args, _, _ = stage_e_args(call)
    if change == "candidate": args["candidate_sha"] = "invalid"
    if change == "rollback": args["rollback_sha"] = args["candidate_sha"]
    if change == "scope": args["scope_sha256"] = "invalid"
    if change == "wrong_freeze": args["freeze_sha256"] = "f" * 64
    if change == "decision": args["affirmative_decision"] = "approve"
    if change == "owner": args["verified_principal"] = "forged"
    if change == "consent": args["exact_owner_consent"] = lambda _: False
    if change == "main": args["protected_main_check"] = lambda _: False
    if change == "claims": args["verify_entra_bearer"] = lambda _: {}
    if change == "signer": args["signer_path"].chmod(0o644)
    if change == "spool": args["requests_path"].chmod(0o777)
    with pytest.raises((PermissionError, ValueError)):
        issuer.issue_stage_e_request(**args)
    assert list(args["requests_path"].iterdir()) == []


def test_production_paths_and_enable_flag_cannot_be_overridden(call):
    args, _, _ = stage_e_args(call)
    args["production"] = True
    with pytest.raises(issuer.StageEMcpBridgeDenied, match="ISSUER_NOT_INSTALLED"):
        issuer.issue_stage_e_request(**args)
    assert list(args["requests_path"].iterdir()) == []


def test_source_profile_is_disabled_and_rollback_disables_issuer():
    root = Path(__file__).resolve().parents[1]
    profile = json.loads((root / "config/pmv4-stage-e-issuer-activation.json").read_text())
    assert profile == {"schema_version": "1.0",
                       "service": "pmv4-stage-e-six-unit-cutover", "mode": "off"}
    script = (root / "infrastructure/jason-mcp/production-deploy.sh").read_text()
    assert 'JASON_PMV4_STAGE_E_ISSUER_ENABLED=false' in script
    assert 'JASON_PMV4_STAGE_E_ISSUER_ENABLED=true' in script
    assert '"${PMV4_STAGE_E_ARGS[@]}"' in script
    server = (root / "implementation/mcp_service/src/jason_mcp/server.py").read_text()
    assert 'def authorize_pmv4_stage_e_cutover(' in server
    assert 'JASON_PMV4_STAGE_E_ISSUER_ENABLED") != "true"' in server
