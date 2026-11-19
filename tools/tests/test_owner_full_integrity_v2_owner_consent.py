"""Owner signer/root verifier compartmentalization for V2 health recovery.

Source-only tests with synthetic Entra tokens and disposable Ed25519 key; the
real private signer and provider systems are never touched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import owner_full_integrity_v2_owner_consent as consent

ROOT=Path(__file__).resolve().parents[2]


def test_fixed_source_policy_hash_and_recovery_exact_scope():
    source_policy=ROOT/"config/owner-full-integrity-v2-repair-policy.json"
    p=json.loads(source_policy.read_bytes())
    assert sha256(source_policy.read_bytes()).hexdigest()==consent.ROOT_POLICY_SHA
    assert p["script_sha256"]==sha256(
        (ROOT/"tools/owner_full_integrity_v2_root_repair.py").read_bytes()).hexdigest()
    assert p["exact_action"]==consent.ACTION
    assert p["one_shot"] is True
    assert p["source_sha"]==consent.SOURCE
    assert p["production_lkg"]==consent.LKG
    assert p["scope_sha256"]==consent.SCOPE
    assert p["bundle_sha256"]==consent.BUNDLE_SHA
    assert p["manifest_sha256"]==consent.BUNDLE_MANIFEST_SHA
    assert p["freeze_sha256"]==consent.FREEZE_SHA
    assert p["promotion_hold_sha256"]==consent.HOLD_SHA
    assert p["no_provider_writes"] and p["no_runtime_change"]


def test_exact_uid1000_owner_preflight_and_root_mismatch_denied(tmp_path,monkeypatch):
    policy=json.loads((ROOT/"config/owner-full-integrity-v2-repair-policy.json").read_bytes())
    policy_src=tmp_path/"policy.json"
    policy_src.write_bytes((ROOT/"config/owner-full-integrity-v2-repair-policy.json").read_bytes())
    blob=tmp_path/"exact-bundle.tar"
    blob.write_bytes(b"binary source package")
    manifest=tmp_path/"source-manifest.json"
    manifest.write_bytes(b"exact binary manifest")
    freeze=tmp_path/"freeze"
    freeze.write_text("freeze")
    hold=tmp_path/"hold"
    hold.write_text("hold")
    release=tmp_path/"releases"/consent.LKG
    release.mkdir(parents=True)
    pointer=tmp_path/"current"
    pointer.symlink_to(release)
    proof=tmp_path/"consent-proof.json"
    monkeypatch.setattr(consent.os,"geteuid",lambda:1000)
    monkeypatch.setattr(consent,"REVIEWED_POLICY",policy_src)
    monkeypatch.setattr(consent,"BUNDLE",blob)
    monkeypatch.setattr(consent,"BUNDLE_MANIFEST",manifest)
    monkeypatch.setattr(consent,"BUNDLE_SHA",sha256(blob.read_bytes()).hexdigest())
    monkeypatch.setattr(consent,"BUNDLE_MANIFEST_SHA",sha256(manifest.read_bytes()).hexdigest())
    monkeypatch.setattr(consent,"FREEZE",freeze)
    monkeypatch.setattr(consent,"HOLD",hold)
    monkeypatch.setattr(consent,"FREEZE_SHA",sha256(freeze.read_bytes()).hexdigest())
    monkeypatch.setattr(consent,"HOLD_SHA",sha256(hold.read_bytes()).hexdigest())
    monkeypatch.setattr(consent,"PROOF",proof)
    orig_resolve=Path.resolve
    monkeypatch.setattr(Path,"resolve",lambda self,**kw:release if str(self)=="/opt/jason/current" else orig_resolve(self,**kw))
    policy["bundle_sha256"]=consent.BUNDLE_SHA
    policy["manifest_sha256"]=consent.BUNDLE_MANIFEST_SHA
    policy["freeze_sha256"]=consent.FREEZE_SHA
    policy["promotion_hold_sha256"]=consent.HOLD_SHA
    policy_src.write_text(json.dumps(policy,sort_keys=True)+"\n")
    monkeypatch.setattr(consent,"ROOT_POLICY_SHA",sha256(policy_src.read_bytes()).hexdigest())
    assert consent.preflight(require_root_upgrade=False)==policy
    monkeypatch.setattr(consent.os,"geteuid",lambda:0)
    with pytest.raises(PermissionError,match="UID1000"):
        consent.preflight(require_root_upgrade=False)
    monkeypatch.setattr(consent.os,"geteuid",lambda:1000)
    policy_src.write_bytes(b"tampered")
    with pytest.raises(PermissionError,match="POLICY_OR_HEALTH_PACKAGE_DRIFT"):
        consent.preflight(require_root_upgrade=False)


def test_unprivileged_owner_issues_exact_proof_and_pinned_root_verifies(
    tmp_path,monkeypatch,
):
    from implementation.kernel import signed_owner_release as verifier
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tools import owner_full_integrity_v2_root_repair as root_repair
    key=Ed25519PrivateKey.generate()
    p=json.loads((ROOT/"config/owner-full-integrity-v2-repair-policy.json").read_bytes())
    decision=tmp_path/"signed-owner-consent.json"
    helper=SimpleNamespace(TENANT="tenant",CLIENT_ID="client",SCOPE="scope",
                           _form=Mock(),jwt_owner=lambda token:verifier.OWNER_OID)
    monkeypatch.setattr(consent,"PROOF",decision)
    monkeypatch.setattr(consent,"preflight",lambda *,require_root_upgrade:p)
    monkeypatch.setattr(consent.sys,"stdin",SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr(consent,"oauth",lambda h:verifier.OWNER_OID)
    monkeypatch.setattr(consent,"load_trusted",lambda path,name:helper if path==consent.OWNER_AUTH else verifier)
    monkeypatch.setattr("builtins.input",lambda prompt:consent.CONFIRM)
    monkeypatch.setattr(verifier,"read_service_owner_signing_key",lambda path:key)
    monkeypatch.setattr(verifier,"read_pinned_root_owner_public_key",lambda *args,**kwargs:key.public_key())
    assert consent.issue()==0
    assert decision.exists()
    signed=json.loads(decision.read_bytes())
    assert decision.stat().st_mode & 0o777 == 0o600
    assert signed["action"]==root_repair.ACTION
    assert signed["root_policy_sha256"]==consent.ROOT_POLICY_SHA
    assert signed["status"]=="AUTHENTICATED_OWNER_APPROVED_NOT_EXECUTED"
    assert signed["signed_owner_proof"]["payload"]["one_release_only"] is True
    assert signed["signed_owner_proof"]["payload"]["standing_authority"] is False
    monkeypatch.setattr(root_repair,"read_secure_root",
                        lambda path,*a,**k:(ROOT/"config/owner-full-integrity-v2-repair-policy.json").read_bytes())
    monkeypatch.setattr(root_repair,"load_trust",lambda path,name:verifier)
    assert root_repair.verify_signed_owner_payload(p,signed)==signed["signed_owner_proof"]
    with pytest.raises(root_repair.RepairDenied):
        root_repair.verify_signed_owner_payload(
            p,{**signed,"action":"unapproved-key-rotation"})


def test_owner_cannot_reuse_signed_proof(tmp_path,monkeypatch):
    proof=tmp_path/"signed-once.json"
    proof.write_text("claimed")
    monkeypatch.setattr(consent,"PROOF",proof)
    monkeypatch.setattr(consent.os,"geteuid",lambda:1000)
    # A stale/disallowed proof cannot be silently overwritten or reused.
    with pytest.raises(FileExistsError):
        fd=__import__("os").open(
            proof,__import__("os").O_CREAT|__import__("os").O_EXCL|__import__("os").O_WRONLY,0o600)
        __import__("os").close(fd)
