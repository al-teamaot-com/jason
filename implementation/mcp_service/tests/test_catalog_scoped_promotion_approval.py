"""Signed Owner catalog release approval: no provider or container writes."""
from __future__ import annotations
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from jason_mcp.catalog_scoped_promotion_approval import (
    queue_catalog_scoped_approval, APPROVAL_WORDS, CatalogScopedApprovalDenied,
)
from kernel.signed_owner_release import verify_exact_owner_release
from tools.catalog_scoped_promotion import make_offer

ROOT=Path(__file__).resolve().parents[3]
MANIFEST=json.loads((ROOT/"config/catalog-scoped-release-admission.json").read_text())
HISTORICAL=json.loads((ROOT/"docs/engineering/evidence/catalog-scope-admission-20261117.json").read_text())
OWNER="person-entra-bee80bdcffb04c50b453c09d4d411f5f"
CLAIMS={"tid":"f7054323-d52b-4863-8c2f-1898f0b6077c",
        "oid":"bee80bdc-ffb0-4c50-b453-c09d4d411f5f"}


def prepared(tmp_path):
    o=make_offer(MANIFEST,HISTORICAL,HISTORICAL)
    path=tmp_path/"offers"/(o["release_id"]+".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(o))
    path.chmod(0o600)
    return o


def issue(state, offer, signer, **overrides):
    args=dict(state_root=state,release_id=offer["release_id"],
        candidate_sha=offer["candidate_sha"],manifest_sha256=offer["manifest_sha256"],
        approved_by=OWNER,organization_id="aot",verified_token_claims=CLAIMS,
        service_signer=signer,affirmative_decision=APPROVAL_WORDS)
    args.update(overrides)
    return queue_catalog_scoped_approval(**args)


def test_fresh_exact_owner_one_use_signature_and_no_release_mutation(tmp_path):
    o=prepared(tmp_path)
    signer=Ed25519PrivateKey.generate()
    receipt=issue(tmp_path,o,signer)
    assert receipt["status"]=="approval_queued_no_deployment"
    assert receipt["owner_approval_is_one_use"] is True
    recorded=json.loads((tmp_path/"owner-approvals"/(o["release_id"]+".json")).read_text())
    from datetime import datetime,timezone
    decision=verify_exact_owner_release(recorded["signed_owner_proof"],
        public_key=signer.public_key(),
        expected_candidate_sha=o["candidate_sha"],expected_rollback_sha=o["rollback_sha"],
        expected_release_id=o["release_id"],expected_scope_sha256=o["scope_sha256"],
        expected_manifest_sha256=o["manifest_sha256"],expected_freeze_sha256=o["freeze_sha256"],
        at=datetime.now(timezone.utc))
    assert decision["owner_principal"]==OWNER
    assert recorded["production_mutation"] is False
    with pytest.raises(CatalogScopedApprovalDenied,match="REPLAY_DENIED"):
        issue(tmp_path,o,signer)


@pytest.mark.parametrize("override",[
    {"affirmative_decision":""},{"affirmative_decision":"approve"},
    {"approved_by":"person-other"},{"organization_id":"other"},
    {"verified_token_claims":{"tid":"foreign","oid":CLAIMS["oid"]}},
    {"verified_token_claims":{"tid":CLAIMS["tid"],"oid":"foreign"}},
    {"service_signer":None},{"candidate_sha":"f"*40},
    {"manifest_sha256":"0"*64},{"release_id":"release-0000000000000000"},
])
def test_invalid_owner_or_scope_never_issues(tmp_path,override):
    o=prepared(tmp_path)
    signer=Ed25519PrivateKey.generate()
    with pytest.raises((CatalogScopedApprovalDenied,ValueError)):
        issue(tmp_path,o,signer,**override)
    approvals=tmp_path/"owner-approvals"
    assert not approvals.exists() or list(approvals.iterdir())==[]


def test_no_offer_cannot_be_signed(tmp_path):
    o=make_offer(MANIFEST,HISTORICAL,HISTORICAL)
    with pytest.raises(CatalogScopedApprovalDenied):
        issue(tmp_path,o,Ed25519PrivateKey.generate())
