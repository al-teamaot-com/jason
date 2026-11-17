"""Nonproduction tests of catalog scoped release authorization and receipt binding."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from uuid import uuid4
from hashlib import sha256
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel.signed_owner_release import issue_exact_owner_release
from tools import catalog_scoped_promotion as p

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "config/catalog-scoped-release-admission.json").read_text())
EVIDENCE = json.loads((ROOT / p.ADMISSION_EVIDENCE_PATH).read_text())
OWNER = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def offer():
    return p.make_offer(MANIFEST, EVIDENCE, EVIDENCE)


def signed(o, key, *, decision="approve"):
    return issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id=o["release_id"], candidate_sha=o["candidate_sha"],
        rollback_sha=o["rollback_sha"], scope_sha256=o["scope_sha256"],
        manifest_sha256=o["manifest_sha256"], freeze_sha256=o["freeze_sha256"],
        verified_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        verified_owner_oid="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        verified_principal=OWNER, verified_organization_id="aot",
        confirmed_decision=decision, at=datetime.now(timezone.utc), private_key=key)


def test_historical_receipt_matches_exact_approved_reference():
    evidence = p.historical_receipt_verified(EVIDENCE, MANIFEST)
    assert evidence["receipt_sha256"] == p.ADMISSION_RECEIPT_SHA256
    assert evidence["rollback_sha"] == MANIFEST["rollback_sha"]


def test_offer_binds_exact_two_images_rollback_and_source():
    o = offer()
    assert set(o) == p.OFFER_FIELDS
    assert o["status"] == "awaiting_exact_owner_approval"
    assert o["candidate_sha"] == MANIFEST["snapshot_sha"]
    assert o["rollback_sha"] == MANIFEST["rollback_sha"]
    assert o["runtime_settings"] == p.RUNTIME_MODE
    assert o["mcp_settings"] == p.MCP_MODE
    assert o["manifest_sha256"] == sha256(p.canonical({k:v for k,v in o.items() if k != "manifest_sha256"})).hexdigest()


@pytest.mark.parametrize("field,bad", [
    ("status", "production_eligible"),
    ("candidate_sha", "a"*40),
    ("rollback_sha", "b"*40),
    ("runtime_image_id", "sha256:"+"f"*64),
    ("mcp_image_id", "sha256:"+"f"*64),
    ("freeze_sha256", "0"*64),
    ("runtime_settings", {"JASON_AUTOTASK_MUTATION_ENABLED":"true"}),
    ("mcp_settings", {"JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES":"person-everyone"}),
    ("one_transaction_only", False),
    ("separate_owner_approval_required", False),
])
def test_offer_modification_denied(field, bad):
    o = offer()
    o[field] = bad
    with pytest.raises(p.ScopedPromotionDenied):
        p.validate_offer(o)


def test_owner_signature_and_replay():
    o = offer()
    signer = Ed25519PrivateKey.generate()
    proof = signed(o, signer)
    decision = p.verify_owner_proof(o, proof, root_pinned_public_key=signer.public_key())
    assert decision["owner_principal"] == OWNER
    with pytest.raises(p.ScopedPromotionDenied):
        p.verify_owner_proof(o, proof, root_pinned_public_key=signer.public_key(), consumed_ids=frozenset({decision["approval_id"]}))
    with pytest.raises(p.ScopedPromotionDenied):
        p.verify_owner_proof(o, proof, root_pinned_public_key=Ed25519PrivateKey.generate().public_key())
    with pytest.raises(p.ScopedPromotionDenied):
        p.verify_owner_proof(o, signed(o,signer,decision="deny"), root_pinned_public_key=signer.public_key())

from contextlib import contextmanager


class FakeHost:
    """Non-network host simulator; all production controls are explicit."""
    def __init__(self, signer, failure=None, rollback_failure=False):
        self.signer=signer
        self.failure=failure
        self.rollback_failure=rollback_failure
        self.events=[]
        self.consumed=set()
        self.breaker=[]
        self.frozen=True
        self.state="baseline"
        self.overlay=False
    def event(self,name):
        self.events.append(name)
        if name==self.failure:
            self.failure=None
            raise RuntimeError("simulated:"+name)
    def enforce_installed_production_trust(self):self.event("installed_root_trust")
    @contextmanager
    def transaction_lock(self,o):
        self.event("production_lock")
        try:yield
        finally:self.events.append("unlock")
    def fresh_source_and_live_admission(self,o):self.event("fresh_source_image_freeze")
    def circuit_breaker_closed_and_workers_quiescent(self):self.event("breaker_closed")
    def deny_unresolved_previous_attempt(self,o):self.event("no_prior_attempt")
    def pinned_owner_public_key(self):
        self.event("pinned_owner_key")
        return self.signer.public_key()
    def consumed_approval_ids(self):
        self.event("replay_ledger")
        return frozenset(self.consumed)
    def protected_container_snapshot(self):
        self.event("other_services_snapshot")
        return {"jason-pmv4-shadow-gateway":"unmodified","openbao":"unmodified"}
    def durable_intent(self,o,decision):self.event("durable_intent")
    def consume_once(self,approval_id):
        self.event("consume_once")
        assert approval_id not in self.consumed
        self.consumed.add(approval_id)
    @contextmanager
    def frozen_one_transaction(self,o,decision):
        self.event("exact_owner_unfreeze")
        self.frozen=False
        try:yield
        finally:
            self.frozen=True
            self.events.append("freeze_restored")
    def promote_exact(self,target,image,revision,setting):
        self.event("deploy_runtime" if target=="jason-runtime" else "deploy_mcp")
        assert revision==o_source()
        assert image==(MANIFEST["runtime_image_id"] if target=="jason-runtime" else MANIFEST["mcp_image_id"])
        assert setting == (p.RUNTIME_MODE if target=="jason-runtime" else p.MCP_MODE)
        self.state=target
    def verify_live_dual_image(self,o):self.event("verify_both_images")
    def verify_unchanged_protected_containers(self,baseline):
        assert baseline["openbao"]=="unmodified"
        self.event("protected_services_unchanged")
    def publish_scoped_control_readback(self,o,decision):
        self.event("publish_control_readback")
        self.overlay=True
    def verify_scoped_control_readback(self,o):self.event("verify_control_readback")
    def rollback_both(self,o):
        self.event("rollback_both")
        if self.rollback_failure:raise RuntimeError("rollback failed")
        self.state="baseline"
    def verify_rollback_and_host(self,o):self.event("verify_rollback")
    def clear_scoped_control_readback(self,o):
        self.event("clear_overlay")
        self.overlay=False
    def record_outcome(self,o,result,*,error=""):
        self.event("record_"+result)
    def freeze_restored_exactly(self,o):
        self.event("verify_freeze_restored")
        if not self.frozen:raise RuntimeError("freeze missing")
    def open_circuit_breaker(self,code):
        self.events.append("open_breaker")
        self.breaker.append(code)


def o_source():return MANIFEST["snapshot_sha"]


def test_dual_image_transaction_success_is_single_use_and_audited():
    o=offer()
    key=Ed25519PrivateKey.generate()
    proof=signed(o,key)
    host=FakeHost(key)
    result=p.promote_scoped_catalog_pair(o,proof,host=host)
    assert result["status"]=="production_pair_verified"
    assert result["provider_test_write_approved"] is False
    assert host.events.index("consume_once") < host.events.index("exact_owner_unfreeze")
    assert host.events.index("deploy_runtime") < host.events.index("deploy_mcp")
    assert host.events.index("verify_both_images") < host.events.index("verify_control_readback")
    assert host.events[-2:]==["verify_freeze_restored","unlock"]
    assert host.state=="jason-mcp-pilot" and host.frozen is True
    with pytest.raises(p.ScopedPromotionDenied,match="OWNER_PROOF_REJECTED"):
        p.promote_scoped_catalog_pair(o,proof,host=host)
    assert host.events.count("deploy_runtime")==1


@pytest.mark.parametrize("phase",["fresh_source_image_freeze","breaker_closed",
    "no_prior_attempt","pinned_owner_key","replay_ledger","other_services_snapshot",
    "durable_intent"])
def test_fail_before_approval_consumption_means_zero_mutations(phase):
    o=offer();key=Ed25519PrivateKey.generate();host=FakeHost(key,failure=phase)
    with pytest.raises(RuntimeError):p.promote_scoped_catalog_pair(o,signed(o,key),host=host)
    assert host.state=="baseline" and host.frozen is True
    assert host.consumed==set()
    assert "deploy_runtime" not in host.events


@pytest.mark.parametrize("phase",["deploy_runtime","deploy_mcp","verify_both_images",
    "protected_services_unchanged","publish_control_readback","verify_control_readback"])
def test_failure_during_pair_promotion_rolls_back_both_and_refreezes(phase):
    o=offer();key=Ed25519PrivateKey.generate();host=FakeHost(key,failure=phase)
    with pytest.raises(RuntimeError):p.promote_scoped_catalog_pair(o,signed(o,key),host=host)
    assert "rollback_both" in host.events
    assert "verify_rollback" in host.events
    assert host.state=="baseline" and host.overlay is False
    assert host.frozen is True and len(host.consumed)==1


def test_rollback_failure_opens_breaker_and_fails_closed():
    o=offer();key=Ed25519PrivateKey.generate();host=FakeHost(key,failure="deploy_mcp",rollback_failure=True)
    with pytest.raises(p.ScopedPromotionDenied,match="ROLLBACK_UNVERIFIED"):
        p.promote_scoped_catalog_pair(o,signed(o,key),host=host)
    assert host.breaker==["CATALOG_SCOPED_ROLLBACK_UNVERIFIED"]
    assert host.frozen is True


def test_freeze_restoration_verification_failure_opens_breaker():
    o=offer();key=Ed25519PrivateKey.generate();host=FakeHost(key,failure="verify_freeze_restored")
    with pytest.raises(RuntimeError):p.promote_scoped_catalog_pair(o,signed(o,key),host=host)
    assert host.breaker==["CATALOG_SCOPED_FREEZE_RESTORATION_UNVERIFIED"]
