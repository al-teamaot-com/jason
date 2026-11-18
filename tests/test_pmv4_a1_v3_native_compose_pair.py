"""Regression: exact candidate Compose != protected A0 rollback Compose.

All tests are disposable, nonroot, without Docker up or live Owner proof.
"""
import copy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from implementation.kernel.signed_owner_release import (
    OWNER_OID, OWNER_PRINCIPAL, TID, canonical, issue_exact_owner_release,
)
from tools.pmv4_shadow_release import (
    ShadowController, ShadowReleaseDenied, bundle_digest, digest_file,
    verify_shadow_compose_pair,
)
from test_pmv4_shadow_release import provision, CANDIDATE, ROLLBACK


@pytest.fixture
def pair(tmp_path):
    legacy=tmp_path/"legacy-compose.yml"
    candidate=tmp_path/"source"/"docker-compose.yml"
    candidate.parent.mkdir()
    legacy.write_bytes(b"root-owned-rollback-profile-512mb-pids64\n")
    candidate.write_bytes(b"sha-bound-activation-profile-2gb-pids256\n")
    return legacy,candidate,digest_file(legacy),digest_file(candidate)


def test_pair_verifies_distinct_exact_hashes(pair):
    legacy,candidate,old_sha,new_sha=pair
    assert old_sha!=new_sha
    assert verify_shadow_compose_pair(
        legacy,candidate,new_sha,old_sha,production=False) is None


def test_old_root_compose_is_not_rewritten_or_confused_with_candidate(pair):
    legacy,candidate,old_sha,new_sha=pair
    original=legacy.read_bytes()
    verify_shadow_compose_pair(legacy,candidate,new_sha,old_sha,production=False)
    assert legacy.read_bytes()==original
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_CANDIDATE_COMPOSE_DRIFT"):
        verify_shadow_compose_pair(legacy,candidate,old_sha,old_sha,production=False)
    assert legacy.read_bytes()==original


def test_legacy_tamper_fails_even_when_candidate_valid(pair):
    legacy,candidate,old_sha,new_sha=pair
    legacy.write_bytes(b"changed-rollback-policy")
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_LEGACY_COMPOSE_DRIFT"):
        verify_shadow_compose_pair(legacy,candidate,new_sha,old_sha,production=False)


def test_candidate_tamper_and_symlink_fail(pair):
    legacy,candidate,old_sha,new_sha=pair
    candidate.write_bytes(b"tampered-candidate-after-review")
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_CANDIDATE_COMPOSE_DRIFT"):
        verify_shadow_compose_pair(legacy,candidate,new_sha,old_sha,production=False)
    candidate.unlink()
    candidate.symlink_to(legacy)
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_CANDIDATE_COMPOSE_MISSING_OR_SYMLINK"):
        verify_shadow_compose_pair(legacy,candidate,new_sha,old_sha,production=False)


@pytest.mark.parametrize("corruption",["bad","f"*63,None])
def test_pair_requires_both_exact_pins(pair,corruption):
    legacy,candidate,old_sha,new_sha=pair
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_COMPOSE_PAIR_HASH_NOT_PINNED"):
        verify_shadow_compose_pair(
            legacy,candidate,new_sha,corruption,production=False)


def test_controller_promotion_preflight_uses_native_candidate_binding(tmp_path):
    root,trust,manifest,proof,at,key=provision(tmp_path)
    legacy=root/"control"/"docker-compose.yml"
    candidate=root/"releases"/CANDIDATE/"bundle"/"config"/"pmv4-shadow"/"docker-compose.yml"
    candidate.parent.mkdir(parents=True,exist_ok=True)
    candidate.write_bytes(b"reviewed-candidate-distinct-2gb-256pids")
    reviewed=root/"control"/"reviewed-scope.json"
    scope=json.loads(reviewed.read_text())
    new_bundle=bundle_digest(root/"releases"/CANDIDATE/"bundle")
    scope["bundle_sha256"]=new_bundle
    reviewed.write_text(json.dumps(scope))
    manifest["bundle_sha256"]=new_bundle
    manifest["scope_sha256"]=sha256(canonical(scope)).hexdigest()
    manifest["compose_sha256"]=digest_file(candidate)
    (root/"releases"/CANDIDATE/"release-manifest.json").write_text(json.dumps(manifest))
    proof=issue_exact_owner_release(
        approval_id="owner-mcp-"+"d"*32,
        release_id="release-"+CANDIDATE[:16],
        candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=sha256(canonical(manifest)).hexdigest(),
        freeze_sha256=digest_file(root/"control"/"shadow-freeze.json"),
        verified_tenant_id=TID,verified_owner_oid=OWNER_OID,
        verified_principal=OWNER_PRINCIPAL,
        verified_organization_id="aot",confirmed_decision="approve",
        at=at,private_key=key,
    )
    controller=ShadowController(
        root,public_key_path=trust,
        protected_ci_check=lambda _:True,
        activate_shadow=lambda _:None,
        verify_shadow_and_core=lambda _:True,
        restore_shadow=lambda _:None,
        production=False,
        compose_binding="candidate",
        legacy_compose_sha256=digest_file(legacy),
    )
    assert manifest["compose_sha256"] != digest_file(legacy)
    authorized=controller.preflight(manifest,proof,at=at)
    assert authorized.candidate_sha==CANDIDATE
    assert authorized.rollback_sha==ROLLBACK
    assert not list((root/"receipts").iterdir())
    assert (root/"current").is_symlink()
    assert (root/"current").readlink().as_posix()=="releases/"+ROLLBACK

    wrong=ShadowController(
        root,public_key_path=trust,
        protected_ci_check=lambda _:True,
        activate_shadow=lambda _:None,
        verify_shadow_and_core=lambda _:True,
        restore_shadow=lambda _:None,
        production=False,
        compose_binding="root",
    )
    with pytest.raises(ShadowReleaseDenied,match="SHADOW_COMPOSE_DRIFT"):
        wrong.preflight(manifest,proof,at=at)
    assert not list((root/"receipts").iterdir())
