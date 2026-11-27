"""Reusable coordinated scoped release: exact authority and rollback tests."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from hashlib import sha256
import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
)
from tools import scoped_backport_coordinated as co
from tools.scoped_backport_release import AOT_TENANT, digest, ScopedBackportDenied


def manifest(names=co.TARGET_ORDER):
    m = {
        "schema_version": "2.0", "profile": "coordinated-core-release",
        "repository": co.REPO, "protected_main_sha": "1"*40,
        "reviewed_feature_sha": "2"*40, "candidate_sha": "3"*40,
        "rollback_sha": "4"*40, "release_id": "release-"+"3"*16,
        "freeze_sha256": "5"*64,
        "projections": {"shared-core": {
            "candidate_sha": "3"*40, "rollback_sha": "4"*40,
            "snapshot_ref": "refs/heads/prep/coordinated-release",
            "changed_files": ["tools/example.py"], "patch_sha256": "6"*64,
        }},
        "targets": [{
            "name": n, "projection": "shared-core",
            "candidate_image": "sha256:"+str(i+1)*64,
            "rollback_image": "sha256:"+str(i+4)*64,
            "rollback_revision": "4"*40,
            "rollback_container_id": str(i+7)*64,
        } for i,n in enumerate(names)],
        "protected_services": sorted(set(co.ALWAYS_PROTECTED) | (set(co.TARGET_ORDER)-set(names))),
        "provider_writes_allowed": False, "standing_authority": False,
    }
    m["scope_sha256"] = digest(m)
    return m


def profile(m):
    return {"schema_version":"2.0", "profile":m["profile"],
            "allowed_targets":[t["name"] for t in m["targets"]],
            "manifest_sha256":digest(m), "root_signed_approval_required":True,
            "preserve_freeze":True}


def proof(m, key, *, at=None, **overrides):
    oid, principal = next(iter(EXACT_OWNER_OAUTH_SUBJECTS.items()))
    args = dict(approval_id="owner-mcp-"+"f"*32, release_id=m["release_id"],
                candidate_sha=m["candidate_sha"], rollback_sha=m["rollback_sha"],
                scope_sha256=m["scope_sha256"], manifest_sha256=digest(m),
                freeze_sha256=m["freeze_sha256"], verified_tenant_id=AOT_TENANT,
                verified_owner_oid=oid, verified_principal=principal,
                verified_organization_id="aot", confirmed_decision="approve",
                at=at or datetime.now(timezone.utc), private_key=key)
    args.update(overrides)
    return issue_exact_owner_release(**args)


class FakeHost:
    def __init__(self, m, key, failures=()):
        self.key = key
        self.live = {t["name"]:t["rollback_image"] for t in m["targets"]}
        self.peers = {name:"same" for name in m["protected_services"]}
        self.failures = list(failures)
        self.events = []
        self.consumed = set()
        self.frozen = True
        self.overlay = False
        self.breaker = False
        self.locked = False
        self.outcomes = []

    def event(self, label):
        self.events.append(label)
        if label in self.failures:
            self.failures.remove(label)
            raise RuntimeError(label)

    def enforce_installed_root_trust(self, p): self.event("trust")
    @contextmanager
    def release_lock(self, m):
        assert not self.locked
        self.locked = True
        self.event("lock")
        try: yield
        finally: self.locked = False
    def freshly_validate_live_scope(self,m): self.event("live")
    def ensure_breaker_closed_and_workers_quiescent(self): self.event("gate")
    def deny_unresolved_attempt(self,m): self.event("prior")
    def owner_public_key(self): return self.key.public_key()
    def consumed_approvals(self): return frozenset(self.consumed)
    def snapshot_protected(self): return dict(self.peers)
    def record_intent(self,m,d,b): self.event("intent")
    def consume_owner_proof(self,a):
        self.event("consume")
        self.consumed.add(a)
    @contextmanager
    def frozen_transaction(self,m,d):
        assert self.locked and self.frozen and d["approval_id"] in self.consumed
        self.event("enter_freeze")
        self.frozen = False
        try: yield
        finally: self.frozen = True
    def promote_exact_target(self,m,t):
        assert self.locked and not self.frozen
        self.event("promote_"+t["name"])
        self.live[t["name"]] = t["candidate_image"]
    def verify_protected_unchanged(self,b):
        self.event("peers")
        assert b == self.peers
    def verify_candidate_targets(self,m):
        self.event("verify_candidates")
        assert self.live == {t["name"]:t["candidate_image"] for t in m["targets"]}
    def publish_component_readback(self,m,d):
        self.event("publish")
        self.overlay = True
    def verify_component_readback(self,m,*,frozen):
        self.event("verify_steady" if frozen else "verify_overlay")
        assert self.overlay and self.frozen == frozen
    def restore_exact_target(self,m,t):
        self.event("restore_"+t["name"])
        self.live[t["name"]] = t["rollback_image"]
    def verify_rollback(self,m):
        self.event("verify_rollback")
        assert self.live == {t["name"]:t["rollback_image"] for t in m["targets"]}
    def clear_component_readback(self,m):
        self.event("clear_overlay")
        self.overlay = False
    def verify_freeze_restored(self,m):
        self.event("freeze_restored")
        assert self.frozen
    def record_outcome(self,m,outcome,error=""):
        self.event("outcome_"+outcome)
        self.outcomes.append(outcome)
    def open_breaker(self,reason):
        self.event("breaker")
        self.breaker = True


@pytest.mark.parametrize("names", [
    ("jason-runtime",), ("jason-runtime","jason-mcp-pilot"), co.TARGET_ORDER,
])
def test_exact_profile_is_reusable(names):
    m=manifest(names)
    assert co.validate_manifest(m) == m
    assert co.validate_profile(profile(m),m) == profile(m)


@pytest.mark.parametrize("field,value", [
    ("standing_authority",True), ("provider_writes_allowed",True),
    ("protected_services",["openbao"]), ("release_id","release-unknown"),
    ("candidate_sha","bad"), ("scope_sha256","6"*64),
])
def test_fail_closed_manifest(field,value):
    m=manifest();m[field]=value
    with pytest.raises(ScopedBackportDenied):co.validate_manifest(m)


@pytest.mark.parametrize("field,value", [
    ("name","openbao"), ("name","jason-pmv4-ticket-core"),
    ("candidate_image","latest"), ("rollback_container_id","arbitrary"),
    ("projection","unknown"), ("rollback_revision","main"),
])
def test_target_validation(field,value):
    m=manifest();m["targets"][0][field]=value
    m["scope_sha256"]=digest(co._scope(m))
    with pytest.raises(ScopedBackportDenied):co.validate_manifest(m)


@pytest.mark.parametrize("change",["duplicate","reverse","extra_field","unused_projection","path_traversal"])
def test_exact_structure(change):
    m=manifest()
    if change=="duplicate":m["targets"].append(deepcopy(m["targets"][0]))
    if change=="reverse":m["targets"].reverse()
    if change=="extra_field":m["targets"][0]["command"]="anything"
    if change=="unused_projection":m["projections"]["unused"]=deepcopy(m["projections"]["shared-core"])
    if change=="path_traversal":m["projections"]["shared-core"]["changed_files"]=["../escape"]
    m["scope_sha256"]=digest(co._scope(m))
    with pytest.raises(ScopedBackportDenied):co.validate_manifest(m)


def test_caller_cannot_expand_pinned_profile():
    m=manifest(); p=profile(m)
    changed=deepcopy(m)
    changed["targets"][0]["candidate_image"]="sha256:"+"e"*64
    changed["scope_sha256"]=digest(co._scope(changed))
    with pytest.raises(ScopedBackportDenied,match="PROFILE_SCOPE"):
        co.validate_profile(p,changed)


def test_all_components_and_freeze_commit_verified():
    m=manifest();key=Ed25519PrivateKey.generate();h=FakeHost(m,key)
    r=co.governed_promote(m,profile(m),proof(m,key),host=h)
    assert r["status"]=="production_components_verified"
    assert h.overlay and h.frozen and not h.breaker
    assert h.events.index("consume") < h.events.index("promote_jason-runtime")
    assert h.events.index("verify_steady") < h.events.index("outcome_production_components_verified")
    assert not h.locked


@pytest.mark.parametrize("fail", [
    "promote_jason-runtime","promote_jason-mcp-pilot","promote_jason-teams-gateway",
    "peers","verify_candidates","publish","verify_overlay",
])
def test_in_window_failure_restores_reverse_order(fail):
    m=manifest();key=Ed25519PrivateKey.generate();h=FakeHost(m,key,[fail])
    with pytest.raises(RuntimeError):co.governed_promote(m,profile(m),proof(m,key),host=h)
    assert h.live=={t["name"]:t["rollback_image"] for t in m["targets"]}
    assert [x for x in h.events if x.startswith("restore_")]==["restore_"+n for n in reversed(co.TARGET_ORDER)]
    assert h.frozen and not h.overlay and not h.breaker
    assert h.outcomes==["rollback_verified"]


@pytest.mark.parametrize("failure",["trust","live","gate","prior","intent","consume"])
def test_early_failure_never_mutates(failure):
    m=manifest();key=Ed25519PrivateKey.generate();h=FakeHost(m,key,[failure])
    with pytest.raises(RuntimeError):co.governed_promote(m,profile(m),proof(m,key),host=h)
    assert not any(x.startswith(("promote_","restore_")) for x in h.events)
    assert h.frozen


@pytest.mark.parametrize("failure",["verify_steady","freeze_restored","outcome_production_components_verified"])
def test_unverified_postflight_opens_breaker_and_requires_recovery(failure):
    m=manifest();key=Ed25519PrivateKey.generate();h=FakeHost(m,key,[failure])
    with pytest.raises(RuntimeError):co.governed_promote(m,profile(m),proof(m,key),host=h)
    assert h.breaker and "recovery_required" in h.outcomes
    assert "production_components_verified" not in h.outcomes


def test_rollback_failure_retains_unresolved_evidence():
    m=manifest();key=Ed25519PrivateKey.generate()
    h=FakeHost(m,key,["promote_jason-teams-gateway","restore_jason-mcp-pilot"])
    with pytest.raises(RuntimeError):co.governed_promote(m,profile(m),proof(m,key),host=h)
    assert h.breaker and "rollback_unverified" in h.outcomes and "recovery_required" in h.outcomes


@pytest.mark.parametrize("kind",["wrong_scope","wrong_manifest","wrong_freeze","expired","wrong_key","replay"])
def test_signed_one_use_binding(kind):
    m=manifest();key=Ed25519PrivateKey.generate();h=FakeHost(m,key)
    kw={}
    if kind=="wrong_scope":kw["scope_sha256"]="e"*64
    if kind=="wrong_manifest":kw["manifest_sha256"]="e"*64
    if kind=="wrong_freeze":kw["freeze_sha256"]="e"*64
    if kind=="expired":kw["at"]=datetime.now(timezone.utc)-timedelta(hours=1)
    if kind=="replay":h.consumed.add("owner-mcp-"+"f"*32)
    signed=proof(m,Ed25519PrivateKey.generate() if kind=="wrong_key" else key,**kw)
    with pytest.raises(ScopedBackportDenied,match="OWNER_PROOF_REJECTED"):
        co.governed_promote(m,profile(m),signed,host=h)
    assert "intent" not in h.events and "consume" not in h.events


def test_source_admission_exact_git_evidence(monkeypatch):
    m=manifest()
    patch=b"exact binary patch"
    m["projections"]["shared-core"]["patch_sha256"]=sha256(patch).hexdigest()
    m["scope_sha256"]=digest(co._scope(m))
    p=profile(m)
    def git(repo,*args):
        if args==("remote","get-url","origin"):return b"https://github.com/al-teamaot-com/jason.git\n"
        if args[0]=="ls-remote":
            if args[-1]=="refs/heads/main":return (m["protected_main_sha"]+"\trefs/heads/main\n").encode()
            return (m["candidate_sha"]+"\t"+args[-1]+"\n").encode()
        if args[:3]==("diff","--no-renames","--name-only"):return b"tools/example.py\n"
        if args[:2]==("diff","--binary"):return patch
        raise AssertionError(args)
    monkeypatch.setattr(co,"_git",git)
    monkeypatch.setattr(co,"_ancestor",lambda *_:True)
    assert co.source_admission(Path("."),m,p)["production_mutations"] is False
    m["projections"]["shared-core"]["patch_sha256"]="e"*64
    m["scope_sha256"]=digest(co._scope(m))
    with pytest.raises(ScopedBackportDenied,match="PROJECTION_SCOPE_DRIFT"):
        co.source_admission(Path("."),m,profile(m))
